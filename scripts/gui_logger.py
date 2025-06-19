#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Activity Logger  (B案 完成版)
macOS 14+ / Python 3.12 対応
"""

import datetime
import os
import subprocess
import tkinter as tk
from tkinter import messagebox

# PyObjC で macOS の Workspace/API を使う
from AppKit import NSWorkspace

LOG_FILE = "activity_log.txt"


class ActivityLogger(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Activity Logger")
        self.geometry("300x160")
        self.resizable(False, False)

        self.running = False
        self.last_app = None

        tk.Button(self, text="▶︎  Start", command=self.start).pack(pady=8, fill="x")
        tk.Button(self, text="■  Stop", command=self.stop).pack(pady=8, fill="x")
        tk.Button(self, text="📝  Show Log", command=self.show_log).pack(pady=8, fill="x")

    # ---- main loop helpers -------------------------------------------------

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._write_log("★ START")
        self._poll_active_app()
        messagebox.showinfo("Logger", "Logging started.")

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self._write_log("★ STOP")
        messagebox.showinfo("Logger", "Logging stopped.")

    def _poll_active_app(self) -> None:
        """1 秒おきにアクティブ App 名をチェック（メインスレッド内）"""
        if not self.running:
            return
        app_name = NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()
        if app_name != self.last_app:
            self.last_app = app_name
            self._write_log(app_name)
        self.after(1000, self._poll_active_app)  # 1000 ms

    # ---- util --------------------------------------------------------------

    def _write_log(self, text: str) -> None:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts}\t{text}\n")

    def show_log(self) -> None:
        path = os.path.abspath(LOG_FILE)
        if not os.path.exists(path):
            messagebox.showinfo("Logger", "Log is empty.")
            return
        try:
            subprocess.run(["open", "-a", "TextEdit", path], check=True)
        except subprocess.CalledProcessError:
            # TextEdit が使えない場合は既定アプリで開く
            subprocess.run(["open", path], check=True)
        except Exception as e:
            messagebox.showerror("Logger", f"ログを開けませんでした:\n{e}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # NOTE: PyObjC を利用するため `pip install pyobjc` が必要です。
    app = ActivityLogger()
    app.mainloop()
