"""
Shared matplotlib plot builders used by both the CLI (`python -m backend.simulation`)
and the Streamlit Simulation page (M8). Kept separate from simulation.py so the
simulation engine has no plotting dependency at import time.
"""
from __future__ import annotations

from typing import List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def graduation_histogram(distribution: List[int], title: str = "Graduation-Time Distribution"):
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(distribution, bins=range(min(distribution), max(distribution) + 2), edgecolor="black")
    ax.set_xlabel("Graduation term (1 = first fall)")
    ax.set_ylabel("Number of students")
    ax.set_title(title)
    fig.tight_layout()
    return fig


def bottleneck_bar_chart(scores: dict, title: str = "Top Bottleneck Courses"):
    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:10]
    codes = [k for k, _ in items]
    values = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(codes[::-1], values[::-1], color="firebrick")
    ax.set_xlabel("Fail + capacity-block events")
    ax.set_title(title)
    fig.tight_layout()
    return fig


def scenario_comparison_bar(results: list, title: str = "Scenario vs Baseline"):
    names = [r["parameter"] for r in results]
    deltas = [r["delta_terms"] or 0 for r in results]
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = ["firebrick" if d > 0 else "seagreen" for d in deltas]
    ax.barh(names[::-1], deltas[::-1], color=colors[::-1])
    ax.set_xlabel("Δ mean graduation term vs. baseline")
    ax.set_title(title)
    fig.tight_layout()
    return fig
