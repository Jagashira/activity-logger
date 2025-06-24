from __future__ import annotations
import ctypes
import datetime as _dt
import signal
import sys
from typing import List
import os
import time
import sqlite3
# --- NEW: Webブラウザと外部コマンド実行のためにインポート ---
import webbrowser
import subprocess

import pyminizip
import objc
from Cocoa import (
    NSObject,
    NSWorkspace,
    NSWorkspaceDidActivateApplicationNotification,
)
from Quartz import *
from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventKeyboardGetUnicodeString,
    CGEventGetIntegerValueField,
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopRemoveSource,
    CFRunLoopGetCurrent,
    CFRunLoopRunInMode,
    CFRunLoopStop,
    kCFRunLoopDefaultMode,
    kCFRunLoopCommonModes,
    kCGSessionEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionDefault,
    kCGEventKeyDown,
    kCGEventFlagsChanged,
    kCGKeyboardEventKeycode,
)
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QTextEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QStatusBar,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QLabel,
    QMessageBox,
    QSystemTrayIcon,
    QAction,
    QMenu,
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import QTimer, pyqtSignal, Qt, QByteArray
from PyQt5.QtSvg import QSvgRenderer

# (DatabaseManager, AppObserver, EventTapManager, flush_buffer, keyboard_cb, create_icon_from_svg のコードは変更なしなので省略)
# (For brevity, the unchanged classes and functions are omitted here.)
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path; os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path); self.cursor = self.conn.cursor(); self._setup_table()
    def _setup_table(self):
        self.cursor.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, event_type TEXT NOT NULL, content TEXT)'); self.conn.commit()
    def add_log_entry(self, event_type: str, content: str = ''):
        timestamp = _dt.datetime.now().isoformat()
        try:
            self.cursor.execute("INSERT INTO logs (timestamp, event_type, content) VALUES (?, ?, ?)", (timestamp, event_type, content)); self.conn.commit()
        except sqlite3.Error as e: print(f"Database error: {e}")
    def close(self):
        if self.conn: self.conn.close()
_buffer: List[str] = []
window: AppWindow = None
def flush_buffer() -> None:
    if not (_buffer and window): return
    text_chunk = ''.join(_buffer); window.db_manager.add_log_entry('KEYSTROKE', text_chunk)
    if window.just_switched_app: log_text = f"\n\u3000{text_chunk}"; window.just_switched_app = False
    else: log_text = text_chunk
    window.update_gui_log(log_text); _buffer.clear()
def keyboard_cb(proxy, etype, event, refcon):
    if etype != kCGEventKeyDown: return event
    _, text = CGEventKeyboardGetUnicodeString(event, 1, None, None)
    keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
    if keycode in (36, 76, 52):
        flush_buffer()
        if window: window.db_manager.add_log_entry('KEYSTROKE', '[ENTER]'); window.update_gui_log("\n")
    elif keycode == 51:
        if _buffer: _buffer.pop()
        else:
            if window: window.db_manager.add_log_entry('KEYSTROKE', '[BACKSPACE]'); window.update_gui_log("[<-]")
    elif keycode == 49: _buffer.append(" ")
    else:
        if text and text.isprintable(): _buffer.append(text)
    return event
class AppObserver(NSObject):
    _current = None
    def didActivateApp_(self, notification):
        app = notification.userInfo()["NSWorkspaceApplicationKey"].localizedName()
        if app != self._current:
            self._current = app; stamp = _dt.datetime.now().strftime("%H:%M:%S"); flush_buffer()
            if window:
                window.db_manager.add_log_entry('APP_SWITCH', app)
                window.update_gui_log(f"\n🗂️  APP  {app}  ({stamp})"); window.just_switched_app = True
    def start(self):
        nc = NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(self, objc.selector(self.didActivateApp_, signature=b"v@:@"), NSWorkspaceDidActivateApplicationNotification, None)
class EventTapManager:
    def __init__(self):
        self.event_tap = None; self.run_loop_source = None; self.app_observer = None; self.is_paused = False
        self.timer = QTimer(); self.timer.setInterval(10); self.timer.timeout.connect(self.poll_events)
    def poll_events(self): CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0, True)
    def is_running(self): return self.timer.isActive()
    def start(self):
        if self.is_running(): return True
        self.event_tap = CGEventTapCreate(kCGSessionEventTap, kCGHeadInsertEventTap, kCGEventTapOptionDefault, (1 << kCGEventKeyDown) | (1 << kCGEventFlagsChanged), keyboard_cb, None)
        if not self.event_tap: return False
        self.run_loop_source = CFMachPortCreateRunLoopSource(None, self.event_tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), self.run_loop_source, kCFRunLoopCommonModes)
        CGEventTapEnable(self.event_tap, True); self.app_observer = AppObserver.alloc().init(); self.app_observer.start(); self.timer.start(); self.is_paused = False
        return True
    def stop(self):
        if not self.is_running(): return
        self.timer.stop()
        if self.app_observer: NSWorkspace.sharedWorkspace().notificationCenter().removeObserver_(self.app_observer); self.app_observer = None
        if self.event_tap: CGEventTapEnable(self.event_tap, False); CFRunLoopRemoveSource(CFRunLoopGetCurrent(), self.run_loop_source, kCFRunLoopCommonModes); self.event_tap = None; self.run_loop_source = None
        self.is_paused = False
    def pause(self):
        if self.is_running() and not self.is_paused: CGEventTapEnable(self.event_tap, False); self.is_paused = True
    def resume(self):
        if self.is_running() and self.is_paused: CGEventTapEnable(self.event_tap, True); self.is_paused = False

class AppWindow(QMainWindow):
    logging_status_changed = pyqtSignal(bool, bool, str)
    def __init__(self):
        super().__init__()
        self.just_switched_app = False
        db_storage_path = os.path.join(os.path.expanduser('~'), ".activity-logger")
        self.db_manager = DatabaseManager(os.path.join(db_storage_path, "activity.db"))
        self.setWindowTitle('Activity Logger'); self.setGeometry(100, 100, 700, 500); self.text_edit = QTextEdit(self); self.text_edit.setReadOnly(True)
        self.toggle_button = QPushButton('Start Logging', self); self.clear_button = QPushButton('Clear Log', self)
        button_layout = QHBoxLayout(); button_layout.addWidget(self.toggle_button); button_layout.addWidget(self.clear_button); button_layout.addStretch(1)
        main_layout = QVBoxLayout(); main_layout.addWidget(self.text_edit); main_layout.addLayout(button_layout)
        container = QWidget(); container.setLayout(main_layout); self.setCentralWidget(container)
        self.statusBar = QStatusBar(self); self.setStatusBar(self.statusBar)
        self.event_manager = EventTapManager()
        self.update_status("Ready. Start logging from the menu bar icon.")
        self.toggle_button.clicked.connect(self.toggle_logging); self.clear_button.clicked.connect(self.text_edit.clear)

    def start_logging(self):
        self.just_switched_app = False
        if self.event_manager.start():
            log_message = "🟢 Logging started..."; self.db_manager.add_log_entry('SYSTEM', 'START'); self.update_gui_log(f"{log_message}\n")
            status_msg = "Status: Logging Active"; self.update_status(status_msg); self.toggle_button.setText("Stop Logging")
            self.logging_status_changed.emit(True, False, status_msg)
        else: self.update_gui_log("❌ FAILED TO CREATE EVENT TAP...\n")
            
    def stop_logging(self):
        flush_buffer(); self.event_manager.stop()
        log_message = "⏹ Logging stopped."; self.db_manager.add_log_entry('SYSTEM', 'STOP'); self.update_gui_log(f"\n{log_message}\n")
        status_msg = "Status: Idle"; self.update_status(status_msg); self.toggle_button.setText("Start Logging")
        self.logging_status_changed.emit(False, False, status_msg)

    def toggle_pause(self):
        if not self.event_manager.is_running(): return
        if self.event_manager.is_paused:
            self.event_manager.resume(); log_message = "▶️ Logging resumed."; event = "RESUME"; is_paused = False; status_msg = "Status: Logging Active"
        else:
            self.event_manager.pause(); log_message = "⏸️ Logging paused."; event = "PAUSE"; is_paused = True; status_msg = "Status: Paused"
        self.db_manager.add_log_entry('SYSTEM', event); self.update_gui_log(f"\n{log_message}\n"); self.update_status(status_msg)
        self.logging_status_changed.emit(True, is_paused, status_msg)

    def toggle_logging(self):
        if self.event_manager.is_running(): self.stop_logging()
        else: self.start_logging()

    # --- NEW: データベースビューアを開くメソッド ---
    def open_database_viewer(self):
        db_viewer_app = "DB Browser for SQLite.app"
        db_viewer_path = os.path.join("/Applications", db_viewer_app)
        download_url = "https://sqlitebrowser.org/dl/"
        db_file_path = self.db_manager.db_path

        if os.path.exists(db_viewer_path):
            # アプリがインストールされている場合
            try:
                self.update_gui_log(f"\nOpening {os.path.basename(db_file_path)} in {db_viewer_app}...")
                subprocess.run(["open", "-a", db_viewer_path, db_file_path], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                self.update_gui_log(f"\nFailed to open database viewer: {e}")
                QMessageBox.critical(self, "Error", f"Could not open the database viewer application at:\n{db_viewer_path}")
        else:
            # アプリがインストールされていない場合
            reply = QMessageBox.question(self, "DB Viewer Not Found",
                                         f"To view the database, '{db_viewer_app}' is recommended.\n\n"
                                         "Would you like to open the download page?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                webbrowser.open(download_url)
                
    def closeEvent(self, event):
        self.hide(); event.ignore()
        
    def update_status(self, message: str): self.statusBar.showMessage(message)
        
    def update_gui_log(self, log_text: str):
        self.text_edit.moveCursor(self.text_edit.textCursor().End); self.text_edit.insertPlainText(log_text); print(log_text, end='', flush=True)

def create_icon_from_svg(svg_template: str, color: str, size: int = 32) -> QIcon:
    svg_data = svg_template.replace('#000000', color); svg_bytes = QByteArray(svg_data.encode('utf-8'))
    renderer = QSvgRenderer(svg_bytes); pixmap = QPixmap(size, size); pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap); renderer.render(painter); painter.end()
    return QIcon(pixmap)

def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    global window
    window = AppWindow()
    
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Systray", "I couldn't detect any system tray on this system."); sys.exit(1)

    app.aboutToQuit.connect(window.db_manager.close)
    
    try:
        script_path = os.path.abspath(__file__); script_dir = os.path.dirname(script_path); project_root = os.path.dirname(script_dir)
        ICON_PATH = os.path.join(project_root, 'asset', 'icon.svg')
        if not os.path.exists(ICON_PATH): raise FileNotFoundError(f"Icon not found at specified path: {ICON_PATH}")
        with open(ICON_PATH, 'r', encoding='utf-8') as f: svg_template_string = f.read()
        COLOR_ACTIVE = "#007AFF"; COLOR_INACTIVE = "#8E8E93"
        icon_active = create_icon_from_svg(svg_template_string, COLOR_ACTIVE); icon_inactive = create_icon_from_svg(svg_template_string, COLOR_INACTIVE)
    except Exception as e:
        print(f"Error setting up icons: {e}"); QMessageBox.warning(None, "Icon Error", f"Could not load icon.\n\nError: {e}")
        icon_active, icon_inactive = QIcon(), QIcon()
        
    tray_icon = QSystemTrayIcon(icon_inactive, parent=app); tray_icon.setToolTip("Activity Logger")
    
    # --- MODIFIED: 新しいメニュー項目を追加 ---
    menu = QMenu()
    status_action = QAction("ステータス: 停止中", menu); status_action.setEnabled(False)
    toggle_log_action = QAction("ロギング開始", menu); toggle_log_action.triggered.connect(window.toggle_logging)
    pause_action = QAction("一時停止", menu); pause_action.triggered.connect(window.toggle_pause); pause_action.setEnabled(False)
    
    menu.addAction(status_action); menu.addSeparator(); menu.addAction(toggle_log_action); menu.addAction(pause_action)
    
    # --- NEW: データベースを開くアクションを追加 ---
    menu.addSeparator()
    view_db_action = QAction("データベースを開く...", menu)
    view_db_action.triggered.connect(window.open_database_viewer)
    menu.addAction(view_db_action)
    
    show_action = QAction("ウィンドウを表示/隠す", menu); show_action.triggered.connect(lambda: window.show() if window.isHidden() else window.hide())
    menu.addAction(show_action)
    
    menu.addSeparator()
    quit_action = QAction("終了", menu); quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    
    tray_icon.setContextMenu(menu); tray_icon.show()
    
    def update_tray_menu(is_logging, is_paused, status_message):
        status_action.setText(f"ステータス: {status_message.replace('Status: ', '')}")
        if not is_logging:
            tray_icon.setIcon(icon_inactive); toggle_log_action.setText("ロギング開始"); pause_action.setText("一時停止"); pause_action.setEnabled(False)
        else:
            toggle_log_action.setText("ロギング停止")
            if is_paused: tray_icon.setIcon(icon_inactive); pause_action.setText("再開"); pause_action.setEnabled(True)
            else: tray_icon.setIcon(icon_active); pause_action.setText("一時停止"); pause_action.setEnabled(True)

    window.logging_status_changed.connect(update_tray_menu)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()