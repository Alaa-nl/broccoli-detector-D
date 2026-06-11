#!/usr/bin/env python3
"""
Integrity manifest tool for the dataset versions in data/registry.json.

Two jobs, both about keeping a dataset version verifiable after the images
leave this repo for blob storage:

  1. Directory mode: walk a dataset directory and write manifest.json with a
     sha256 + size for every file. The manifest is written into the dataset
     directory by default so it travels inside the zip - anyone who downloads
     the archive later can prove that no image or label file was lost or
     altered in transit.

  2. --archive mode: hash an existing .zip and print the digest in a form
     that pastes straight into the archive_sha256 field of data/registry.json.

Standard library only, on purpose: this must run on whatever Python a
teammate already has on their laptop (3.9 included), with no virtualenv.
"""

import argparse
import hashlib
import json
from pathlib import Path

# Hash in chunks so a multi-gigabyte archive never has to fit in RAM.
CHUNK_BYTES = 1024 * 1024


def sha256_of(path):
    """Return the hex sha256 of a file, read in CHUNK_BYTES pieces."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(dataset_dir, version, out_dir):
    """Walk dataset_dir and write <out_dir>/manifest.json. Returns its path."""
    out_path = out_dir / "manifest.json"
    entries = []
    total_bytes = 0
    # Sorted walk: the manifest must be byte-identical across runs and
    # machines, otherwise re-running the tool would look like a data change.
    for path in sorted(dataset_dir.rglob("*")):
        if not path.is_file():
            continue
        # Skip OS junk (.DS_Store and friends) and any previous manifest:
        # neither is part of the dataset, and including them would make the
        # manifest churn without the actual data changing.
        if path.name.startswith(".") or path.resolve() == out_path.resolve():
            continue
        size = path.stat().st_size
        entries.append(
            {
                "path": path.relative_to(dataset_dir).as_posix(),
                "sha256": sha256_of(path),
                "bytes": size,
            }
        )
        total_bytes += size

    manifest = {
        "dataset_version": version,
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "files": entries,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    return out_path, len(entries), total_bytes


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Write an integrity manifest for a dataset directory, and/or "
            "print the sha256 of a dataset archive for data/registry.json."
        ),
        epilog=(
            "Typical flow: run on the dataset directory first (manifest ends "
            "up inside the zip), zip it, then run --archive on the zip and "
            "paste the digest into data/registry.json."
        ),
    )
    parser.add_argument(
        "dataset_dir",
        nargs="?",
        type=Path,
        help="dataset directory to walk; omit when only hashing an archive",
    )
    parser.add_argument(
        "--version",
        help="dataset version string recorded in the manifest, "
        "e.g. broccoli-rgb-v1 (required with dataset_dir)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="directory to write manifest.json into (default: the dataset "
        "directory itself, so the manifest gets zipped with the images)",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        help="hash this .zip and print its sha256 for the archive_sha256 "
        "field of data/registry.json",
    )
    args = parser.parse_args()

    if args.dataset_dir is None and args.archive is None:
        parser.error("nothing to do: pass a dataset directory, --archive, or both")

    if args.dataset_dir is not None:
        if args.version is None:
            parser.error("--version is required when writing a manifest")
        if not args.dataset_dir.is_dir():
            parser.error("not a directory: {}".format(args.dataset_dir))
        out_dir = args.out if args.out is not None else args.dataset_dir
        out_path, count, total = build_manifest(
            args.dataset_dir, args.version, out_dir
        )
        print("Wrote {} ({} files, {} bytes)".format(out_path, count, total))

    if args.archive is not None:
        if not args.archive.is_file():
            parser.error("archive not found: {}".format(args.archive))
        digest = sha256_of(args.archive)
        print("sha256({}) = {}".format(args.archive.name, digest))
        print('data/registry.json line:  "archive_sha256": "{}"'.format(digest))


if __name__ == "__main__":
    main()
