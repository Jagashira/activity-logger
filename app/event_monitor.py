# app/event_monitor.py (Fixed)

from __future__ import annotations
from typing import List
import datetime as _dt

import objc
from Cocoa import NSObject, NSWorkspace, NSWorkspaceDidActivateApplicationNotification
from Quartz import *

from Quartz import (
    CGEventTapCreate, CGEventTapEnable, CGEventKeyboardGetUnicodeString,
    CGEventGetIntegerValueField, CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource, CFRunLoopRemoveSource, CFRunLoopGetCurrent,
    CFRunLoopRunInMode, kCFRunLoopDefaultMode, kCGSessionEventTap,
    kCGHeadInsertEventTap, kCGEventTapOptionDefault, kCGEventKeyDown,
    kCGEventFlagsChanged, kCGKeyboardEventKeycode, kCFRunLoopCommonModes
)
from PyQt5.QtCore import QObject, pyqtSignal, QTimer


_event_manager_instance = None
_buffer: List[str] = []

def keyboard_cb(proxy, etype, event, refcon):
    global _event_manager_instance
    if etype != kCGEventKeyDown or not _event_manager_instance:
        return event

    _, text = CGEventKeyboardGetUnicodeString(event, 1, None, None)
    keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)

    if keycode in (36, 76, 52):
        _event_manager_instance.flush_buffer()
        _event_manager_instance.log_event_received.emit('KEYSTROKE', '[ENTER]')
        _event_manager_instance.gui_log_received.emit("\n")
    elif keycode == 51:
        if _buffer:
            _buffer.pop()
        else:
            _event_manager_instance.log_event_received.emit('KEYSTROKE', '[BACKSPACE]')
            _event_manager_instance.gui_log_received.emit("[<-]")
    elif keycode == 49:
        _buffer.append(" ")
    else:
        if text and text.isprintable():
            _buffer.append(text)
    return event

class AppObserver(NSObject):
    def didActivateApp_(self, notification):
        global _event_manager_instance
        if not _event_manager_instance: return

        _event_manager_instance.flush_buffer()
        app_name = notification.userInfo()["NSWorkspaceApplicationKey"].localizedName()
        
        if app_name != _event_manager_instance.last_app_name:
            _event_manager_instance.last_app_name = app_name
            stamp = _dt.datetime.now().strftime("%H:%M:%S")
            _event_manager_instance.log_event_received.emit('APP_SWITCH', app_name)
            _event_manager_instance.gui_log_received.emit(f"\n🗂️  APP  {app_name}  ({stamp})")
            _event_manager_instance.just_switched_app = True

class EventTapManager(QObject):
    log_event_received = pyqtSignal(str, str)
    gui_log_received = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        global _event_manager_instance
        _event_manager_instance = self
        
        self.event_tap = None
        self.run_loop_source = None
        self.app_observer = None
        self.is_paused = False
        self.last_app_name = ""
        self.just_switched_app = False

        self.timer = QTimer()
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.poll_events)

    def flush_buffer(self):
        global _buffer
        if not _buffer: return
        
        text_chunk = ''.join(_buffer)
        self.log_event_received.emit('KEYSTROKE', text_chunk)
        
        if self.just_switched_app:
            log_text = f"\n\u3000{text_chunk}"
            self.just_switched_app = False
        else:
            log_text = text_chunk
            
        self.gui_log_received.emit(log_text)
        _buffer.clear()

    def poll_events(self):
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0, True)

    def is_running(self):
        return self.timer.isActive()

    def start(self):
        if self.is_running(): return True
        mask = (1 << kCGEventKeyDown) | (1 << kCGEventFlagsChanged)
        self.event_tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap,
                                          kCGEventTapOptionDefault, mask, keyboard_cb, None)
        if not self.event_tap: return False
        
        self.run_loop_source = CFMachPortCreateRunLoopSource(None, self.event_tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), self.run_loop_source, kCFRunLoopCommonModes)
        CGEventTapEnable(self.event_tap, True)
        
        self.app_observer = AppObserver.alloc().init()
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(self.app_observer,
                                             objc.selector(self.app_observer.didActivateApp_, signature=b"v@:@"),
                                             NSWorkspaceDidActivateApplicationNotification, None)
        self.timer.start()
        self.is_paused = False
        return True

    def stop(self):
        if not self.is_running(): return
        self.flush_buffer()
        self.timer.stop()
        if self.app_observer:
            NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self.app_observer)
            self.app_observer = None
        if self.event_tap:
            CGEventTapEnable(self.event_tap, False)
            CFRunLoopRemoveSource(CFRunLoopGetCurrent(), self.run_loop_source, kCFRunLoopCommonModes)
            self.event_tap = None
            self.run_loop_source = None
        self.is_paused = False

    def pause(self):
        if self.is_running() and not self.is_paused:
            CGEventTapEnable(self.event_tap, False); self.is_paused = True

    def resume(self):
        if self.is_running() and self.is_paused:
            CGEventTapEnable(self.event_tap, True); self.is_paused = False
