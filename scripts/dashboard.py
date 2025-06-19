#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
activity_dashboard.py – Visualise your macOS activity-logger output
-------------------------------------------------------------------
Usage examples
--------------
# 単一ログファイル
python activity_dashboard.py ~/activity_logs/log_20250619_120507.txt 2025-06-19

# ログフォルダ（同日の log_YYYYMMDD_*.txt をすべて集計）
python activity_dashboard.py ~/activity_logs 2025-06-19

生成物
------
カレントディレクトリに   activity_report_YYYY-MM-DD.html   を出力します。

必要パッケージ
--------------
pip install pandas plotly
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys
from typing import Iterable, List, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# 正規表現（walrus を使わず linters 互換に）-----------------------------------
# ---------------------------------------------------------------------------

APP_RE = re.compile(r"^🗂️\s+APP\s+(?P<app>.+?)\s+\((?P<time>\d{2}:\d{2}:\d{2})\)")
TXT_RE = re.compile(r"^TXT\s+(?P<text>.*)")


# ---------------------------------------------------------------------------
# パース処理 ------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _parse_one(path: pathlib.Path, day: dt.date) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    単一ログファイル *path* を対象日 *day* として解析し、
    (sessions, keystrokes) の 2 DataFrame を返す。
    """
    sessions: List[Tuple[str, dt.datetime, dt.datetime]] = []
    strokes: List[Tuple[str, int, dt.datetime]] = []

    current_app: str | None = None
    current_start: dt.datetime | None = None

    with path.open(encoding="utf-8", errors="replace") as fp:
        for raw in fp:
            line = raw.rstrip("\n")

            m_app = APP_RE.match(line)
            if m_app is not None:
                # 前セッションをクローズ
                wall_time = dt.datetime.strptime(m_app.group("time"), "%H:%M:%S").time()
                now_dt = dt.datetime.combine(day, wall_time)

                if current_app is not None and current_start is not None:
                    sessions.append((current_app, current_start, now_dt))

                # 新セッション開始
                current_app = m_app.group("app")
                current_start = now_dt
                continue

            m_txt = TXT_RE.match(line)
            if m_txt is not None and current_app and current_start:
                strokes.append((current_app, len(m_txt.group("text")), current_start))

    # ファイル終端 – 当日 23:59:59 まで延長してクローズ
    if current_app and current_start:
        eod = dt.datetime.combine(day, dt.time(23, 59, 59))
        sessions.append((current_app, current_start, eod))

    df_sessions = pd.DataFrame(sessions, columns=["app", "start", "end"])
    df_keyst = pd.DataFrame(strokes, columns=["app", "chars", "time"])
    return df_sessions, df_keyst


# ---------------------------------------------------------------------------
# レポート生成 ----------------------------------------------------------------
# ---------------------------------------------------------------------------

def _build_report(
    df_sessions: pd.DataFrame,
    df_keyst: pd.DataFrame,
    day: dt.date,
    out_html: pathlib.Path,
) -> None:
    """Plotly で HTML ダッシュボードを生成する。"""

    # ----- アプリ使用時間 ---------------------------------------------------
    df_sessions["duration_min"] = (
        df_sessions["end"] - df_sessions["start"]
    ).dt.total_seconds() / 60
    app_hours = (
        df_sessions.groupby("app", sort=False)["duration_min"]
        .sum()
        .sort_values()
        / 60.0
    )

    fig1 = px.bar(
        app_hours,
        orientation="h",
        title="Time spent per application (hours)",
        labels={"value": "Hours", "index": "Application"},
    )

    # ----- キーストローク量 --------------------------------------------------
    if not df_keyst.empty:
        df_keyst["slot"] = df_keyst["time"].dt.floor("30min")
        ks = df_keyst.groupby("slot")["chars"].sum().reset_index()
        fig2 = px.bar(
            ks,
            x="slot",
            y="chars",
            title="Keystrokes per 30-minute slot",
            labels={"slot": "Time", "chars": "Keystrokes"},
        )
    else:
        fig2 = go.Figure()
        fig2.update_layout(title="No keystroke data for the selected day")

    # ----- サブプロット合成 --------------------------------------------------
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=False,
        vertical_spacing=0.18,
        subplot_titles=(
            fig1.layout.title.text,
            fig2.layout.title.text,
        ),
    )

    for trace in fig1.data:
        fig.add_trace(trace, row=1, col=1)
    for trace in fig2.data:
        fig.add_trace(trace, row=2, col=1)

    fig.update_layout(
        height=900,
        showlegend=False,
        title_text=f"Activity report – {day}",
    )
    fig.write_html(out_html, include_plotlyjs="cdn")
    print(f"✅  Report saved to {out_html}")


# ---------------------------------------------------------------------------
# CLI ------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _cli(argv: Iterable[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Visualise activity-logger output")
    p.add_argument(
        "logfile",
        type=pathlib.Path,
        help="Path to log file *or* directory containing logs",
    )
    p.add_argument(
        "date",
        type=lambda s: dt.datetime.strptime(s, "%Y-%m-%d").date(),
        help="Date to analyse (YYYY-MM-DD)",
    )
    ns = p.parse_args(argv)

    if not ns.logfile.exists():
        sys.exit(f"Path not found: {ns.logfile}")

    # ----- ファイル収集 -----------------------------------------------------
    if ns.logfile.is_dir():
        ymd = ns.date.strftime("%Y%m%d")
        pattern = f"log_{ymd}_*.txt"
        paths = sorted(ns.logfile.glob(pattern))
        if not paths:
            sys.exit(f"No log matching {pattern!r} under {ns.logfile}")
    else:
        paths = [ns.logfile]

    # ----- 解析 → DataFrame 連結 -------------------------------------------
    sess_parts: List[pd.DataFrame] = []
    key_parts: List[pd.DataFrame] = []
    for path in paths:
        df_s, df_k = _parse_one(path, ns.date)
        sess_parts.append(df_s)
        key_parts.append(df_k)

    sessions = (
        pd.concat(sess_parts, ignore_index=True) if sess_parts else pd.DataFrame()
    )
    keystrokes = (
        pd.concat(key_parts, ignore_index=True) if key_parts else pd.DataFrame()
    )

    # ----- レポート出力 ------------------------------------------------------
    outfile = pathlib.Path(f"activity_report_{ns.date}.html")
    _build_report(sessions, keystrokes, ns.date, outfile)


if __name__ == "__main__":
    _cli()
