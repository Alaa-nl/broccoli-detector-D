#!/bin/bash
# Entrypoint for the single-container Azure image (Dockerfile.azure).
# Renders the nginx config from the shared template, then runs uvicorn and
# nginx side by side and dies if either one dies, so the platform's restart
# policy handles recovery instead of the container limping along half-broken.
set -euo pipefail

# Default the five template vars. They line up with the ENV defaults baked
# into the image, but defaulting here too keeps the script correct even if
# someone clears the environment. API_KEY defaults to empty: nginx then sends
# an empty X-API-Key header, which a keyless backend ignores (same behaviour
# as local dev in the two-container setup).
export BACKEND_SCHEME="${BACKEND_SCHEME:-http}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export DNS_RESOLVER="${DNS_RESOLVER:-1.1.1.1 1.0.0.1}"
export API_KEY="${API_KEY:-}"

# Render the template the same way the official nginx image's entrypoint
# would. The quoted var list restricts envsubst to exactly these five vars;
# without it, envsubst would also blank out nginx runtime variables in the
# template ($request_uri, $remote_addr, ...) because they look like unset
# shell variables.
envsubst '${BACKEND_SCHEME} ${BACKEND_HOST} ${BACKEND_PORT} ${DNS_RESOLVER} ${API_KEY}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

# Start the API bound to loopback only: the container publishes just port 80,
# and inside it nothing but nginx can reach uvicorn — so the X-API-Key
# injection and security headers cannot be bypassed, preserving the exact
# trust boundary of the two-container setup (where the backend port simply
# isn't exposed to the outside).
#
# This script runs as root (nginx needs it for port 80), so drop uvicorn to
# appuser via setpriv (util-linux, present in python:3.11-slim): the process
# that parses untrusted images and deserializes model weights must not be
# root. Single worker and --limit-concurrency 32 for the same reasons spelled
# out in backend/Dockerfile.
setpriv --reuid=appuser --regid=appuser --init-groups \
    uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}" --limit-concurrency 32 &
UVICORN_PID=$!

# nginx in the foreground ("daemon off;"), backgrounded by the shell so we
# can supervise both children below. Master stays root, workers drop to
# www-data per Debian's nginx.conf.
nginx -g "daemon off;" &
NGINX_PID=$!

# Forward shutdown signals to both children: uvicorn finishes in-flight
# requests and nginx drains connections, instead of the kernel SIGKILLing
# them as orphans the moment PID 1 (this script) exits. Matters on
# `docker stop` and on Container Apps revision swaps.
trap 'kill -TERM "$UVICORN_PID" "$NGINX_PID" 2>/dev/null' TERM INT

# Block until the FIRST child exits (or a shutdown signal fires the trap),
# stop the other one, reap both, and exit with the first child's status.
# Either way the container stops as a unit and the platform restarts it —
# half-alive states never serve traffic.
STATUS=0
wait -n || STATUS=$?
kill -TERM "$UVICORN_PID" "$NGINX_PID" 2>/dev/null || true
wait || true
exit "$STATUS"
