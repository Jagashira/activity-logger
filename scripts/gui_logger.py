#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Activity & Keystroke Logger  (B案 + キー入力)
macOS 11+ / Apple Silicon / Python 3.12
"""

import datetime
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox

# PyObjC
from AppKit import NSWorkspace
from Quartz import (
    CGEventTapCreate, kCGHIDEventTap, kCGHeadInsertEventTap,
    kCGEventKeyDown, kCGEventTapOptionDefault, CFRunLoopAddSource,
    CFMachPortCreateRunLoopSource, CFRunLoopGetCurrent, CGEventTapEnable,
    CGEventKeyboardGetUnicodeString, CFRunLoopRun
)
import Quartz  # name-space access用

LOG_FILE = "activity_log.txt"


# -------------------------------------------------------------------------
class KeyTapThread(threading.Thread):
    """Quartz Event-Tap でキー入力を横取りし、Queue に文字を push する"""

    def __init__(self, q: queue.Queue):
        super().__init__(daemon=True)
        self.q = q

    def run(self):
        # --- イベントタップ callback ------------------------------------
        def _callback(proxy, etype, event, refcon):
            if etype != kCGEventKeyDown:
                return event
            # UTF-16LE で取得 → Python str へ
            n, buf = CGEventKeyboardGetUnicodeString(event, 0, None, None)
            if n:
                # decode は bytes 型が欲しいので memoryview へ
                s = memoryview(buf).tobytes().decode("utf-16le")
                # 改行・タブを可視化
                printable = s.replace("\n", "⏎").replace("\r", "")
                self.q.put(printable)
            return event

        # --- Event Tap 作成 ----------------------------------------------
        mask = 1 << kCGEventKeyDown
        tap = CGEventTapCreate(
            kCGHIDEventTap,           # 物理キーボード層
            kCGHeadInsertEventTap,    # 最上位
            kCGEventTapOptionDefault,
            mask,
            _callback,
            None
        )
        if not tap:
            self.q.put("[!] EventTap 生成失敗（権限？）")
            return

        # --- RunLoop に登録して回し続ける -------------------------------
        src = CFMachPortCreateRunLoopSource(None, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopCommonModes)
        CGEventTapEnable(tap, True)
        CFRunLoopRun()


# -------------------------------------------------------------------------
class ActivityLogger(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Activity + Keystroke Logger")
        self.geometry("320x180")
        self.resizable(False, False)

        self.running = False
        self.last_app = None
        self.key_queue: queue.Queue[str] = queue.Queue()

        tk.Button(self, text="▶︎  Start", command=self.start).pack(pady=6, fill="x")
        tk.Button(self, text="■  Stop",  command=self.stop).pack(pady=6, fill="x")
        tk.Button(self, text="📝  Show Log", command=self.show_log).pack(pady=6, fill="x")

    # ---- controls --------------------------------------------------------
    def start(self):
        if self.running:
            return
        # ⇨ Event-tap スレッド起動
        KeyTapThread(self.key_queue).start()
        self.running = True
        self._write_log("★ START")
        self._poll()
        messagebox.showinfo("Logger", "Logging started.\n\n⚠️  初回は「入力監視」を許可してください。")

    def stop(self):
        if not self.running:
            return
        self.running = False
        self._write_log("★ STOP")
        messagebox.showinfo("Logger", "Logging stopped.")

    # ---- main polling ----------------------------------------------------
    def _poll(self):
        if not self.running:
            return

        # 1) アクティブ App
        app_name = NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()
        if app_name != self.last_app:
            self.last_app = app_name
            self._write_log(f"[APP] {app_name}")

        # 2) たまったキー入力を flush
        while not self.key_queue.empty():
            ch = self.key_queue.get_nowait()
            self._write_log(f"[KEY] {ch}")

        self.after(200, self._poll)   # 0.2 秒間隔

    # ---- utils -----------------------------------------------------------
    def _write_log(self, text: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts}\t{text}\n")

    def show_log(self):
        path = os.path.abspath(LOG_FILE)
        if not os.path.exists(path):
            messagebox.showinfo("Logger", "Log is empty.")
            return
        try:
            subprocess.run(["open", "-a", "TextEdit", path], check=True)
        except subprocess.CalledProcessError:
            subprocess.run(["open", path], check=True)
        except Exception as e:
            messagebox.showerror("Logger", f"ログを開けませんでした:\n{e}")


# -------------------------------------------------------------------------
def _check_permissions() -> bool:
    """
    Quartz Event-Tap が使えるか粗チェック。
    アクセス拒否だと tap は None になるので、事前に警告を出す。
    """
    tap = CGEventTapCreate(
        kCGHIDEventTap, kCGHeadInsertEventTap,
        kCGEventTapOptionDefault, 1 << kCGEventKeyDown,
        lambda *args: args[-2], None
    )
    ok = bool(tap)
    if tap:
        Quartz.CFMachPortInvalidate(tap)  # すぐ破棄
    return ok


if __name__ == "__main__":
    if not _check_permissions():
        tk.Tk().withdraw()
        messagebox.showerror(
            "権限が必要",
            "キー入力を取得するには\n"
            "システム設定 → プライバシーとセキュリティ → 入力監視\n"
            "でこの Python を “許可” してください。"
        )
        raise SystemExit(1)

    app = ActivityLogger()
    app.mainloop()
