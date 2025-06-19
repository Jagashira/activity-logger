#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macOS Activity‑Logger  (App‑switch + Keystroke buffer)
-----------------------------------------------------
• Before running, grant *Terminal* (or the Python interpreter you use)
  both “Accessibility” **and** “Input Monitoring” permissions in
  *Settings › Privacy & Security*.
• Press **Ctrl‑C** in the terminal window to stop the logger safely.

What you get on stdout
---------------------
🗂️  APP  Google Chrome        # ← whenever the front‑most app changes
TXT  Hello world               # ← whole lines, flushed on   ↩︎  (Return)

Special keys handled
--------------------
Return  … flushes current buffer and prints it
Delete  … deletes last character in buffer
Other   … appended to buffer as received (Unicode)
"""

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

class AppObserver(NSObject):
    """Posts a message whenever the active application changes."""

    def init(self):
        self = objc.super(AppObserver, self).init()
        if self is None:
            return None
        self._current = None  # type: str | None
        return self

    # selector has a single colon → one explicit arg (notification)
    def didActivateApp_(self, notification):  # noqa: N802 (PyObjC naming conv.)
        app = notification.userInfo()["NSWorkspaceApplicationKey"].localizedName()
        if app != self._current:
            self._current = app
            stamp = _dt.datetime.now().strftime("%H:%M:%S")
            flush_buffer()  # flush any partial line before app switch
            print(f"\n🗂️  APP  {app}  ({stamp})")

    def start(self):
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(
            self,
            objc.selector(self.didActivateApp_, signature=b"v@:@"),
            NSWorkspaceDidActivateApplicationNotification,
            None,
        )


# --- Keystroke tap --------------------------------------------------------------

# Mask: listen for KeyDown + FlagsChanged (⇧ / ⌥…) events
_MASK = (1 << kCGEventKeyDown) | (1 << kCGEventFlagsChanged)

# a mutable buffer we will fill with characters until a Return key is hit
_buffer: List[str] = []


def flush_buffer() -> None:
    """Print the current buffer as one line and clear it."""
    if _buffer:
        text = "".join(_buffer)
        print(f"TXT  {text}")
        _buffer.clear()


def keyboard_cb(proxy, etype, event, refcon):  # noqa: ANN001 (Quartz API sig.)
    if etype != kCGEventKeyDown:
        return event  # Ignore other types (FlagsChanged etc.)

    # Get a *single* Unicode string representing the key press
    _, text = CGEventKeyboardGetUnicodeString(event, 255, None, None)
    keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

    # Handle special keys ------------------------------------------------------
    if keycode in (36, 76):  # Return / Enter
        flush_buffer()
    elif keycode == 51:  # Delete / Backspace
        if _buffer:
            _buffer.pop()
    else:
        if text:
            _buffer.append(text)
    return event


# --- Main ----------------------------------------------------------------------

def main() -> None:  # noqa: D401 – imperative mood
    # 1. Create and enable the event tap
    tap = CGEventTapCreate(
        kCGSessionEventTap,
        kCGHeadInsertEventTap,
        kCGEventTapOptionDefault,
        _MASK,
        keyboard_cb,
        None,
    )
    if tap is None:
        sys.exit(
            "❌  CGEventTapCreate failed. Check Accessibility / Input‑Monitoring permissions."
        )

    src = CFMachPortCreateRunLoopSource(None, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes)
    CGEventTapEnable(tap, True)

    # 2. Start application‑switch observer
    observer = AppObserver.alloc().init()
    observer.start()

    # 3. Stop handler (Ctrl‑C)
    def _stop(sig, frame):  # noqa: D401, ANN001 – signal handler sig, frame
        print("\n⏹  Stopping …")
        flush_buffer()
        CGEventTapEnable(tap, False)
        CFRunLoopStop(CFRunLoopGetCurrent())

    signal.signal(signal.SIGINT, _stop)

    print("🟢  Start logging …  (Ctrl‑C to quit)")
    CFRunLoopRun()


if __name__ == "__main__":
    # Quartz type marshaling relies on ctypes – make sure it's imported *before* main
    import ctypes as _ctypes  # noqa: F401  (kept for clarity)

    main()