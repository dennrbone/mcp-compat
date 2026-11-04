"""Рисунки итоговых документов из проверенных сохранённых оценок."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]


def build(output):
    result = json.loads((ROOT/"experiments/final-comparison-2026-11-05/analysis.json").read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({"font.family": "DejaVu Serif", "font.size": 10,
                         "svg.hashsalt": "mcp-final-publication"}):
        fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.4), constrained_layout=True)
        for axis, methods, title in zip(axes, [("A", "B", "C", "D", "E"), ("FULL", "NO_FINAL")],
                                      ["Сохранённый V2", "Парная абляция"]):
            rates = [result["summary"][m]["classification"]["FAR"] for m in methods]
            axis.bar(methods, [r["value"] for r in rates], color="#66516b")
            axis.set_ylim(0, 1.12)
            axis.set_title(title, fontsize=11)
            axis.set_ylabel("FAR")
            axis.tick_params(axis="x", labelrotation=20)
            for i, r in enumerate(rates):
                axis.text(i, r["value"]+.025, f'{r["numerator"]}/{r["denominator"]}', ha="center", fontsize=9)
        fig.savefig(output/"candidate-far.png", dpi=320, metadata={"Software": "MCP-Compat"})
        fig.savefig(output/"candidate-far.svg", metadata={"Date": None})
        plt.close(fig)
        fig, axis = plt.subplots(figsize=(6.5, 3.3), constrained_layout=True)
        methods = ("FULL", "NO_FINAL")
        values = [result["summary"][m]["classification"] for m in methods]
        bottom = [0, 0]
        for key, label, color in [("TP", "Корректный допуск", "#47795a"),
                                  ("FP", "Неверный допуск", "#b84e4e"),
                                  ("TN", "Корректный отказ", "#9baab8")]:
            counts = [v[key] for v in values]
            axis.barh(methods, counts, left=bottom, label=label, color=color)
            for i, n in enumerate(counts):
                if n:
                    axis.text(bottom[i]+n/2, i, str(n), ha="center", va="center", color="white" if key!="TN" else "black")
            bottom = [b+n for b, n in zip(bottom, counts)]
        assert all(v["FN"] == 0 for v in values)
        axis.set_xlim(0, 63)
        axis.set_xlabel("Число фиксированных кандидатов")
        axis.legend(loc="upper center", bbox_to_anchor=(.5, -.25), ncol=2, frameon=False)
        fig.savefig(output/"final-admission.png", dpi=320, metadata={"Software": "MCP-Compat"})
        fig.savefig(output/"final-admission.svg", metadata={"Date": None})
        plt.close(fig)
    for name in ("candidate-far.svg", "final-admission.svg"):
        path = output/name
        path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines())+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT/"docs/publication/figures")
    build(parser.parse_args().output)
