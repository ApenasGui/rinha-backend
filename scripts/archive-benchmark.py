#!/usr/bin/env python3
"""Archive a completed synthetic benchmark, refusing to replace any evidence."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile


ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "summary.json": "summary.json",
    "environment.json": "environment.json",
    "docker-limits.json": "docker-limits.json",
    "tools.json": "tools.json",
    "resource-samples.jsonl": "resource-samples.jsonl",
    "time-series.json": "time-series.json",
    "initial-count.txt": "initial-count.txt",
    "contagem-pessoas.log": "final-count.txt",
    "gatling-exit-code.txt": "gatling-exit-code.txt",
}
LOGS = ("gatling.log", "docker-before.log", "docker-after.log")
OPTIONAL_FILES = (
    "run-status.json",
    "source-integrity.json",
    "final-count-exit-code.txt",
    "runtime-after.json",
)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def compress(source, destination):
    with source.open("rb") as original, destination.open("xb") as output:
        # Omit machine paths and timestamps from the gzip header.
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
            shutil.copyfileobj(original, compressed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="Completed directory under benchmark/results")
    parser.add_argument("--output-root", type=Path, default=ROOT / "benchmark/evidence")
    arguments = parser.parse_args()
    run = arguments.run.resolve(strict=True)
    if not run.is_dir():
        parser.error("run must be a directory")
    required = [*(run / name for name in FILES), *(run / name for name in LOGS)]
    missing = [str(path) for path in required if not path.is_file()]
    reports = sorted((run / "gatling").glob("*/index.html"))
    if len(reports) != 1:
        parser.error(f"Expected exactly one Gatling report, found {len(reports)}")
    report = reports[0].parent
    missing.extend(str(report / name) for name in ("simulation.log", "js/global_stats.json", "js/stats.json") if not (report / name).is_file())
    if missing:
        parser.error("Missing completed-run artifacts: " + ", ".join(missing))
    summary = json.loads((run / "summary.json").read_text())
    expected_log_hash = summary.get("simulation_log_sha256")
    actual_log_hash = sha256(report / "simulation.log")
    if expected_log_hash != actual_log_hash:
        parser.error("simulation.log SHA256 does not match summary.json; refusing to archive")
    final_count = int((run / "contagem-pessoas.log").read_text())
    if summary.get("person_count") != final_count:
        parser.error("Final count does not match summary.json")
    if summary.get("gatling_exit_code") != int((run / "gatling-exit-code.txt").read_text()):
        parser.error("Gatling exit code does not match summary.json")

    output_root = arguments.output_root.resolve()
    if output_root == run or output_root.is_relative_to(run):
        parser.error("Evidence must be written outside the source run")
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / run.name
    try:
        # Reserve the final directory exclusively, including against concurrent runs.
        destination.mkdir(exist_ok=False)
    except FileExistsError:
        parser.error(f"Evidence already exists; nothing overwritten: {destination}")

    try:
        for source_name, destination_name in FILES.items():
            with (run / source_name).open("rb") as source, (destination / destination_name).open("xb") as target:
                shutil.copyfileobj(source, target)
        for name in LOGS:
            compress(run / name, destination / (name + ".gz"))
        optional = {run / name for name in OPTIONAL_FILES}
        optional.update(run.glob("diagnostic-*"))
        optional.update(run.glob("runtime-*.json"))
        optional.add(run / "final-count-error.log")
        for source in sorted(optional):
            if not source.is_file():
                continue
            if source.suffix == ".log":
                compress(source, destination / (source.name + ".gz"))
            else:
                with source.open("rb") as original, (destination / source.name).open("xb") as target:
                    shutil.copyfileobj(original, target)
        with (destination / "gatling-report.tar.gz").open("xb") as target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w|") as archive:
                    archive.add(report, arcname=report.name, recursive=True)
        artifacts = {
            path.name: {"sha256": sha256(path), "bytes": path.stat().st_size}
            for path in sorted(destination.iterdir()) if path.is_file()
        }
        manifest = {
            "schema_version": 1,
            "source_run": run.name,
            "archived_at_utc": datetime.now(timezone.utc).isoformat(),
            "official_commit": summary.get("official_commit"),
            "person_count": final_count,
            "simulation_log_sha256": actual_log_hash,
            "report_directory": report.name,
            "artifacts": artifacts,
            "integrity": "SHA256SUMS covers all artifacts and this manifest; its own checksum is excluded.",
        }
        with (destination / "manifest.json").open("x") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        with (destination / "SHA256SUMS").open("x") as stream:
            for path in sorted(destination.iterdir()):
                if path.is_file() and path.name != "SHA256SUMS":
                    stream.write(f"{sha256(path)}  {path.name}\n")
        print(destination)
    except BaseException:
        # Keep partial evidence visible and prevent a later invocation replacing it.
        with (destination / "INCOMPLETE.txt").open("x") as stream:
            stream.write("Archiving was interrupted. This directory is incomplete and will never be overwritten automatically.\n")
        print(f"Incomplete evidence retained at {destination}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
