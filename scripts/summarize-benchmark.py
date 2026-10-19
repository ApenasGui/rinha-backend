#!/usr/bin/env python3
"""Keep Gatling's statistics and a small, auditable request time series."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys


def request_stats(stats):
    total, failed = stats["numberOfRequests"]["total"], stats["numberOfRequests"]["ko"]
    return {
        "requests": total,
        "ok": stats["numberOfRequests"]["ok"],
        "ko": failed,
        "error_rate_percent": round(100 * failed / total, 4) if total else 0,
        "requests_per_second": stats["meanNumberOfRequestsPerSecond"]["total"],
        "latency_ms": {
            **{name: stats[key]["total"] for name, key in (("min", "minResponseTime"), ("mean", "meanResponseTime"), ("p50", "percentiles1"), ("p75", "percentiles2"), ("p95", "percentiles3"), ("p99", "percentiles4"), ("max", "maxResponseTime"))},
            "p99_ok": stats["percentiles4"]["ok"],
        },
    }


def main():
    run = Path(sys.argv[1]).resolve()
    reports = sorted(run.glob("gatling/*/js/global_stats.json"))
    if len(reports) != 1:
        raise RuntimeError(f"Esperava exatamente um relatório Gatling; encontrados {len(reports)}")
    report = reports[0].parent.parent
    global_stats = json.loads(reports[0].read_text())
    full_stats = json.loads((report / "js/stats.json").read_text())
    simulation = report / "simulation.log"
    bins = defaultdict(lambda: {"ok": 0, "ko": 0, "latencies": []})
    errors = defaultdict(int)
    first_request, last_request = None, None
    with simulation.open() as stream:
        for line in stream:
            fields = line.rstrip("\n").split("\t")
            if fields[0] != "REQUEST":
                continue
            start, end = int(fields[3]), int(fields[4])
            first_request = min(first_request, start) if first_request is not None else start
            last_request = max(last_request, end) if last_request is not None else end
            bucket = bins[(start // 5000) * 5000]
            bucket[fields[5].lower()] += 1
            bucket["latencies"].append(end - start)
            if fields[5] == "KO":
                errors[fields[6] if len(fields) > 6 else "unknown"] += 1
    points = []
    for timestamp, bucket in sorted(bins.items()):
        latencies = sorted(bucket.pop("latencies"))
        points.append({"seconds": round((timestamp - (first_request // 5000) * 5000) / 1000, 3), **bucket, "p95_ms": latencies[math.ceil(0.95 * len(latencies)) - 1]})
    run_status_path = run / "run-status.json"
    source_integrity_path = run / "source-integrity.json"
    run_status = json.loads(run_status_path.read_text()) if run_status_path.is_file() else None
    source_integrity = json.loads(source_integrity_path.read_text()) if source_integrity_path.is_file() else None
    gatling_exit_code = int((run / "gatling-exit-code.txt").read_text())
    verified = (
        run_status is not None and run_status.get("valid") is True
        and source_integrity is not None and source_integrity.get("unchanged") is True
        and gatling_exit_code == 0
    )
    summary = {
        "label": json.loads((run / "environment.json").read_text())["label"],
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "gatling_exit_code": gatling_exit_code,
        "validity": "valid" if verified else "invalid" if run_status is not None else "unverified",
        "validation": {
            "run_status_valid": run_status.get("valid") if run_status is not None else None,
            "source_unchanged": source_integrity.get("unchanged") if source_integrity is not None else None,
            "note": "KO requests and application saturation are reported as measurements; they do not invalidate the run.",
        },
        "person_count": int((run / "contagem-pessoas.log").read_text()),
        "measured_duration_seconds": round((last_request - first_request) / 1000, 3),
        "global": request_stats(global_stats),
        "requests": {entry["name"]: request_stats(entry["stats"]) for entry in full_stats.get("contents", {}).values() if entry["type"] == "REQUEST"},
        "errors": dict(sorted(errors.items(), key=lambda item: item[1], reverse=True)),
        "report": str(report.relative_to(run) / "index.html"),
        "simulation_log_sha256": hashlib.sha256(simulation.read_bytes()).hexdigest(),
        "official_commit": json.loads((run / "tools.json").read_text())["source"]["commit"],
        "comparability": "Local reproduction; hardware differs from the official 2023 run. This is not an official ranking entry.",
    }
    (run / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    (run / "time-series.json").write_text(json.dumps(points, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
