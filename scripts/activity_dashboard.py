#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
activity_dashboard.py – Visualize your macOS activity-logger output
-------------------------------------------------------------------
Usage
-----
    python activity_dashboard.py LOGFILE.txt 2025-06-19
    # → creates   activity_report_2025-06-19.html in the cwd

What it expects
---------------
A plain-text log produced by the logger we built (APP switch & TXT lines), e.g.:

    🗂️  APP  Google Chrome  (10:44:09)
    TXT  print("hello world")
    TXT  foo = 42
    …

Requirements
------------
    pip install pandas plotly
"""

import argparse
import datetime as dt
import pathlib
import re
import sys
from typing import Iterable, List, Tuple

import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go

# Regex helpers
APP_RE = re.compile(r"^🗂️\s+APP\s+(?P<app>.+?)\s+\((?P<time>\d{2}:\d{2}:\d{2})\)")
TXT_RE = re.compile(r"^TXT\s+(?P<text>.*)")

# Parsing function
def parse_log(path: pathlib.Path, day: dt.date) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (sessions, keystrokes) DataFrames for *one* day."""

    sessions: List[Tuple[str, dt.datetime, dt.datetime]] = []
    strokes: List[Tuple[str, int, dt.datetime]] = []

    current_app: str | None = None
    current_start: dt.datetime | None = None

    with path.open(encoding="utf-8", errors="replace") as fp:
        for raw in fp:
            line = raw.rstrip("\n")

            m_app = APP_RE.match(line)
            if m_app is not None:
                # Close previous session (if any)
                wall_time = dt.datetime.strptime(m_app.group("time"), "%H:%M:%S").time()
                t_now = dt.datetime.combine(day, wall_time)

                if current_app is not None and current_start is not None:
                    sessions.append((current_app, current_start, t_now))

                # Start new session
                current_app = m_app.group("app")
                current_start = t_now
                continue  # proceed to next line

            m_txt = TXT_RE.match(line)
            if m_txt is not None and current_app and current_start:
                strokes.append((current_app, len(m_txt.group("text")), current_start))

    # close the last session at end‑of‑day
    if current_app and current_start:
        eod = dt.datetime.combine(day, dt.time(23, 59, 59))
        sessions.append((current_app, current_start, eod))

    df_sessions = pd.DataFrame(sessions, columns=["app", "start", "end"])
    df_keyst = pd.DataFrame(strokes, columns=["app", "chars", "time"])
    return df_sessions, df_keyst

# Report building function
def build_report(df_sessions: pd.DataFrame, df_keyst: pd.DataFrame, day: dt.date, out_html: pathlib.Path) -> None:
    """Create an interactive HTML dashboard with Plotly."""

    # App usage (hours)
    df_sessions["duration_min"] = (df_sessions["end"] - df_sessions["start"]).dt.total_seconds() / 60
    app_hours = (
        df_sessions.groupby("app", sort=False)["duration_min"].sum().sort_values()
        / 60.0
    )

    fig1 = px.bar(
        app_hours,
        orientation="h",
        title="Time spent per application (hours)",
        labels={"value": "Hours", "index": "Application"},
    )

    # Keystroke histogram
    if not df_keyst.empty:
        df_keyst["slot"] = df_keyst["time"].dt.floor("30min")
        ks = df_keyst.groupby("slot")["chars"].sum().reset_index()
        fig2 = px.bar(
            ks,
            x="slot",
            y="chars",
            title="Keystrokes per 30‑minute slot",
            labels={"slot": "Time", "chars": "Keystrokes"},
        )
    else:
        fig2 = go.Figure()
        fig2.update_layout(title="No keystroke data for the selected day")

    # Combine in a single page
    fig = make_subplots(rows=2, cols=1, shared_xaxes=False, vertical_spacing=0.18, subplot_titles=(fig1.layout.title.text, fig2.layout.title.text))

    for trace in fig1.data:
        fig.add_trace(trace, row=1, col=1)
    for trace in fig2.data:
        fig.add_trace(trace, row=2, col=1)

    fig.update_layout(height=900, showlegend=False, title_text=f"Activity report – {day}")
    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"✅  Report saved to {out_html}")

# CLI function
def _cli(argv: Iterable[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Visualise activity‑logger output")
    p.add_argument("logfile", type=pathlib.Path, help="Path to plain‑text log file")
    p.add_argument("date", type=lambda s: dt.datetime.strptime(s, "%Y-%m-%d").date(), help="Date to analyse (YYYY-MM-DD)")
    ns = p.parse_args(argv)

    if not ns.logfile.exists():
        sys.exit(f"Log file not found: {ns.logfile}")

    sessions, keyst = parse_log(ns.logfile, ns.date)
    outfile = pathlib.Path(f"activity_report_{ns.date}.html")
    build_report(sessions, keyst, ns.date, outfile)

if __name__ == "__main__":
    _cli()
