#!/usr/bin/env python3
"""Render exportable figures from measured runs; needs matplotlib."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".local/matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".local/cache"))
Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument("runs", nargs="+", type=Path)
parser.add_argument("--output", type=Path, default=ROOT / "benchmark/comparison")
arguments = parser.parse_args()
summaries = [json.loads((run / "summary.json").read_text()) for run in arguments.runs]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
figure, axes = plt.subplots(2, 2, figsize=(14, 10), layout="constrained")
colors = ["#e76f51", "#218380", "#4b66c2", "#9b5de5"]
display_labels = {"baseline-host": "Varredura\nsem cache", "indexed-cache-host": "Índice + cache\nRAM original", "tuned-host": "Banco: 0,85 CPU\nAPIs: 0,25 CPU", "memory-host": "Nginx: 256 MiB\nCPU original"}
labels = [display_labels.get(summary["label"], summary["label"]) for summary in summaries]
counts = [summary["person_count"] for summary in summaries]
bars = axes[0, 0].bar(labels, counts, color=colors[:len(summaries)], width=0.55)
axes[0, 0].bar_label(bars, labels=[f"{value:,}".replace(",", ".") for value in counts], padding=4)
axes[0, 0].set(title="Pessoas persistidas ao final", ylabel="Registros no PostgreSQL")
axes[0, 0].axhline(44936, color="#6b7280", linestyle="--", linewidth=1, label="Vencedor de 2023: 44.936*")
axes[0, 0].set_ylim(0, max(*counts, 44936) * 1.18)
axes[0, 0].legend(frameon=False, fontsize=9, loc="upper left")
for index, (run, summary) in enumerate(zip(arguments.runs, summaries)):
    series = json.loads((run / "time-series.json").read_text())
    color = colors[index % len(colors)]
    axes[0, 1].plot([point["seconds"] for point in series], [(point["ok"] + point["ko"]) / 5 for point in series], label=summary["label"], color=color)
    axes[1, 0].plot([point["seconds"] for point in series], [point["p95_ms"] for point in series], label=summary["label"], color=color)
axes[0, 1].set(title="Requisições iniciadas por segundo", xlabel="Tempo (s)", ylabel="req/s — janelas de 5 s")
axes[1, 0].set(title="Latência p95 por janela", xlabel="Tempo (s)", ylabel="ms — janelas de 5 s")
for axis in (axes[0, 1], axes[1, 0]):
    axis.legend(frameon=False)
    axis.grid(alpha=0.15)
axes[1, 1].axis("off")
lines = ["Gatling 3.9.5 • carga oficial integral (205 s)", "Aplicação: 2 APIs + Nginx + PostgreSQL", "Limite total: 1,5 CPU e até 3 GB", ""]
for run, summary in zip(arguments.runs, summaries):
    stats = summary["global"]
    runtime_path = run / 'runtime-after.json'
    oom = sum(c['memory_events']['oom_kill'] for c in json.loads(runtime_path.read_text())['containers'].values()) if runtime_path.exists() else '?'
    lines.extend([f"{summary['label']}: {stats['requests']:,} requests; {stats['error_rate_percent']:.2f}% KO", f"p95: {stats['latency_ms']['p95']:,} ms; p99 OK: {stats['latency_ms']['p99_ok']:,} ms; OOM: {oom}", ""])
lines.extend(["* Referência histórica: hardware oficial diferente.", "Execuções locais no mesmo host; sem equivalência", "de hardware com o ranking de 2023.", "Uma execução por configuração; resultado exploratório."])
axes[1, 1].text(0.02, 0.97, "\n".join(lines), va="top", fontsize=10, linespacing=1.5)
figure.suptitle("Rinha de Backend 2023 Q3 — NestJS", fontsize=18, fontweight="bold")
arguments.output.parent.mkdir(parents=True, exist_ok=True)
for extension in ("svg", "png"):
    path = arguments.output.with_suffix("." + extension)
    figure.savefig(path, dpi=160, metadata={"Creator": "scripts/plot-benchmarks.py"})
    print(path)
