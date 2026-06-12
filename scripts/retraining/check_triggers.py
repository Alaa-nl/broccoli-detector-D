#!/usr/bin/env python3
"""Evaluate the retraining triggers against live Prometheus metrics.

Turns the monitored metrics into a retraining decision: four instant queries
against the Prometheus HTTP API, each compared to a threshold, printed as a
table (or --json for machines). Exit code 0 = nothing triggered, 1 = at least
one trigger fired, 2 = Prometheus unreachable or setup error - so cron/CI can
run this on a schedule and alert on a non-zero exit.

Standard library only on purpose: this must run on a bare host python (3.9+),
no virtualenv, because the whole point is that anyone on the team can check
the triggers without setting anything up.

Triggers (full rationale in docs/retraining.md):
  T1  mean detection confidence over the window dropped below --min-confidence
  T2  share of detect calls returning zero crowns rose above --max-empty-rate
  T3  median crown diameter drifted more than --max-diameter-drift (fraction)
      from the baseline in baseline.json
  T4  HTTP 5xx error rate above --max-error-rate - an OPS alert, not a model
      alert: investigate the service first, a broken service is not a drifted
      model.
"""

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_PROM_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
DEFAULT_BASELINE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "baseline.json"
)

# Trigger states. INSUFFICIENT_DATA is deliberately not a failure: a quiet
# field (no uploads overnight) must not page anyone or start a retrain.
OK = "OK"
TRIGGERED = "TRIGGERED"
INSUFFICIENT = "INSUFFICIENT DATA"


class PrometheusError(Exception):
    """Raised when Prometheus cannot be queried; maps to exit code 2."""


def query_instant(prom_url, promql, timeout_s=10.0):
    """Run one instant query; return its scalar value, or None for no data.

    Prometheus answers histogram_quantile over an empty range with NaN rather
    than an empty result, so NaN/Inf are normalised to None here - callers
    then report INSUFFICIENT DATA instead of comparing against NaN (which
    would silently evaluate every threshold to False).
    """
    url = "{0}/api/v1/query?{1}".format(
        prom_url.rstrip("/"), urllib.parse.urlencode({"query": promql})
    )
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PrometheusError(
            "Could not query Prometheus at {0}: {1}\n"
            "Is the monitoring stack running? (Prometheus default: "
            "http://localhost:9090, override with --prom-url or "
            "PROMETHEUS_URL)".format(prom_url, exc)
        )
    if payload.get("status") != "success":
        raise PrometheusError(
            "Prometheus rejected query {0!r}: {1}".format(
                promql, payload.get("error", "unknown error")
            )
        )
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    value = float(result[0]["value"][1])
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def load_baseline(path):
    try:
        with open(path) as fh:
            baseline = json.load(fh)
    except (OSError, ValueError) as exc:
        raise PrometheusError(
            "Could not load baseline file {0}: {1}".format(path, exc)
        )
    if "diameter_p50_mm" not in baseline:
        raise PrometheusError(
            "Baseline file {0} is missing 'diameter_p50_mm' - T3 cannot be "
            "evaluated without a reference median.".format(path)
        )
    return baseline


def _fmt(value, digits=3):
    return "n/a" if value is None else "{0:.{1}f}".format(value, digits)


def evaluate(prom_url, window, baseline, args):
    """Run all four trigger checks and return a list of result dicts."""
    triggers = []

    # T1: mean confidence from the histogram's own _sum/_count - cheaper and
    # more honest than averaging bucket midpoints.
    mean_conf = query_instant(
        prom_url,
        "rate(broccoli_detection_confidence_sum[{w}])"
        " / rate(broccoli_detection_confidence_count[{w}])".format(w=window),
    )
    if mean_conf is None:
        status, note = INSUFFICIENT, "no detections in the window"
    elif mean_conf < args.min_confidence:
        status, note = TRIGGERED, (
            "model is unsure about what it finds - likely new field "
            "conditions; collect + annotate recent uploads"
        )
    else:
        status, note = OK, ""
    triggers.append({
        "id": "T1",
        "name": "low mean confidence",
        "observed": _fmt(mean_conf),
        "observed_value": mean_conf,
        "threshold": "< {0:.2f} triggers".format(args.min_confidence),
        "status": status,
        "note": note,
    })

    # T2: increase() rather than rate() so the threshold reads as a fraction
    # of actual requests. Gated on a minimum request count: 2 empty results
    # out of 3 uploads is noise, not drift.
    requests_1h = query_instant(
        prom_url,
        "increase(broccoli_detection_requests_total[{w}])".format(w=window),
    )
    empty_rate = None
    if requests_1h is None or requests_1h < args.min_requests:
        observed = "n/a"
        status = INSUFFICIENT
        note = "only {0} detect requests in the window (need >= {1})".format(
            0 if requests_1h is None else int(round(requests_1h)),
            args.min_requests,
        )
    else:
        empties = query_instant(
            prom_url,
            "increase(broccoli_empty_detections_total[{w}])".format(w=window),
        ) or 0.0
        empty_rate = empties / requests_1h
        observed = _fmt(empty_rate)
        if empty_rate > args.max_empty_rate:
            status, note = TRIGGERED, (
                "model finds nothing in a large share of images - check "
                "recent uploads for conditions absent from the training set"
            )
        else:
            status, note = OK, ""
    triggers.append({
        "id": "T2",
        "name": "empty-result rate",
        "observed": observed,
        "observed_value": empty_rate,
        "threshold": "> {0:.2f} triggers".format(args.max_empty_rate),
        "status": status,
        "note": note,
    })

    # T3: median crown diameter vs. the captured baseline. The median (not the
    # mean) so a handful of mis-scaled outliers can't fake a drift.
    base_p50 = float(baseline["diameter_p50_mm"])
    p50 = query_instant(
        prom_url,
        "histogram_quantile(0.5,"
        " rate(broccoli_crown_diameter_mm_bucket[{w}]))".format(w=window),
    )
    drift = None
    if p50 is None:
        observed, status = "n/a", INSUFFICIENT
        note = "no crowns measured in the window"
    else:
        drift = abs(p50 - base_p50) / base_p50
        observed = "p50 {0:.0f}mm (drift {1:.0%})".format(p50, drift)
        if drift > args.max_diameter_drift:
            status, note = TRIGGERED, (
                "size distribution moved vs. baseline ({0:.0f}mm) - new "
                "growth stage, cultivar, or a wrong camera_height_mm "
                "setting; verify the camera height before blaming the model"
            ).format(base_p50)
        else:
            status, note = OK, ""
    triggers.append({
        "id": "T3",
        "name": "diameter p50 drift",
        "observed": observed,
        "observed_value": drift,
        "threshold": "> {0:.0%} from {1:.0f}mm".format(
            args.max_diameter_drift, base_p50
        ),
        "status": status,
        "note": note,
    })

    # T4: server-side error rate. Lives here because a dying backend also
    # drags T1/T2 around (failed requests never reach the ML counters), so
    # the ops signal must be visible next to the ML ones.
    total_rate = query_instant(
        prom_url,
        "sum(rate(broccoli_http_requests_total[{w}]))".format(w=window),
    )
    ratio = None
    if total_rate is None or total_rate == 0:
        observed, status = "n/a", INSUFFICIENT
        note = "no HTTP traffic in the window"
    else:
        err_rate = query_instant(
            prom_url,
            'sum(rate(broccoli_http_requests_total{{status=~"5.."}}'
            "[{w}]))".format(w=window),
        ) or 0.0
        ratio = err_rate / total_rate
        observed = _fmt(ratio)
        if ratio > args.max_error_rate:
            status, note = TRIGGERED, (
                "OPS alert, not a model alert: investigate the service "
                "(logs, /api/health, resources) before considering "
                "retraining - a broken service is not a drifted model"
            )
        else:
            status, note = OK, ""
    triggers.append({
        "id": "T4",
        "name": "HTTP 5xx error rate (ops)",
        "observed": observed,
        "observed_value": ratio,
        "threshold": "> {0:.2f} triggers".format(args.max_error_rate),
        "status": status,
        "note": note,
    })

    return triggers


def print_table(prom_url, window, baseline_path, triggers):
    rows = [("TRIGGER", "OBSERVED", "THRESHOLD", "STATUS")]
    for t in triggers:
        rows.append((
            "{0} {1}".format(t["id"], t["name"]),
            t["observed"],
            t["threshold"],
            t["status"],
        ))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    print("Retraining triggers  -  {0}  -  window {1}".format(
        prom_url, window
    ))
    print("Baseline: {0}".format(baseline_path))
    print()
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    notes = [t for t in triggers if t["status"] != OK and t["note"]]
    if notes:
        print()
        for t in notes:
            print("{0}: {1}".format(t["id"], t["note"]))


def main():
    parser = argparse.ArgumentParser(
        description="Check the BroccoliDetect retraining triggers against "
                    "Prometheus. Exit 0 = all clear, 1 = trigger(s) fired, "
                    "2 = Prometheus unreachable.",
    )
    parser.add_argument(
        "--prom-url", default=DEFAULT_PROM_URL,
        help="Prometheus base URL (default %(default)s, or PROMETHEUS_URL)",
    )
    parser.add_argument(
        "--baseline", default=DEFAULT_BASELINE,
        help="Path to baseline.json (default: next to this script)",
    )
    # The default 1h window matches how a cron job would run this; demos use
    # a short window (e.g. --window 15m) so a burst from simulate_drift.py
    # isn't diluted by an hour of normal traffic.
    parser.add_argument(
        "--window", default="1h",
        help="PromQL range window for all queries (default %(default)s)",
    )
    parser.add_argument(
        "--min-confidence", type=float, default=0.55,
        help="T1: minimum acceptable mean confidence (default %(default)s)",
    )
    parser.add_argument(
        "--max-empty-rate", type=float, default=0.30,
        help="T2: maximum acceptable empty-result fraction "
             "(default %(default)s)",
    )
    parser.add_argument(
        "--min-requests", type=int, default=20,
        help="T2: minimum detect requests in the window before the empty "
             "rate is meaningful (default %(default)s)",
    )
    parser.add_argument(
        "--max-diameter-drift", type=float, default=0.25,
        help="T3: maximum fractional deviation of the diameter median from "
             "the baseline (default %(default)s)",
    )
    parser.add_argument(
        "--max-error-rate", type=float, default=0.05,
        help="T4: maximum acceptable 5xx fraction (default %(default)s)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of the table",
    )
    args = parser.parse_args()

    try:
        baseline = load_baseline(args.baseline)
        triggers = evaluate(args.prom_url, args.window, baseline, args)
    except PrometheusError as exc:
        print("ERROR: {0}".format(exc), file=sys.stderr)
        sys.exit(2)

    any_triggered = any(t["status"] == TRIGGERED for t in triggers)
    if args.json:
        print(json.dumps({
            "prometheus_url": args.prom_url,
            "window": args.window,
            "baseline_file": args.baseline,
            "triggers": triggers,
            "any_triggered": any_triggered,
        }, indent=2))
    else:
        print_table(args.prom_url, args.window, args.baseline, triggers)
    sys.exit(1 if any_triggered else 0)


if __name__ == "__main__":
    main()
