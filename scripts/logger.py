# scripts/logger.py

from __future__ import annotations
import ctypes
import datetime as _dt
import signal
import sys
from typing import List, Dict
import os
import time
import sqlite3
import webbrowser
import subprocess
from collections import defaultdict
import json

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
    QMessageBox,
    QSystemTrayIcon,
    QAction,
    QMenu,
    QLabel,
    QFrame,
    QStackedWidget,
    QCheckBox,
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import QTimer, pyqtSignal, Qt, QByteArray
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWebEngineWidgets import QWebEngineView


def resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except Exception: base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base_path, relative_path)
class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path; os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False); self.cursor = self.conn.cursor(); self._setup_table()
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
    window.log_message_received.emit(log_text); _buffer.clear()
def keyboard_cb(proxy, etype, event, refcon):
    if etype != kCGEventKeyDown: return event
    _, text = CGEventKeyboardGetUnicodeString(event, 1, None, None)
    keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
    if keycode in (36, 76, 52):
        flush_buffer()
        if window: window.db_manager.add_log_entry('KEYSTROKE', '[ENTER]'); window.log_message_received.emit("\n")
    elif keycode == 51:
        if _buffer: _buffer.pop()
        else:
            if window: window.db_manager.add_log_entry('KEYSTROKE', '[BACKSPACE]'); window.log_message_received.emit("[<-]")
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
                window.log_message_received.emit(f"\n🗂️  APP  {app}  ({stamp})"); window.just_switched_app = True
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
def create_icon_from_svg(svg_template: str, color: str, size: int = 32) -> QIcon:
    svg_data = svg_template.replace('#000000', color); svg_bytes = QByteArray(svg_data.encode('utf-8'))
    renderer = QSvgRenderer(svg_bytes); pixmap = QPixmap(size, size); pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap); renderer.render(painter); painter.end()
    return QIcon(pixmap)


class ConfigManager:
    def __init__(self, path):
        self.path = path
        self.defaults = {
            'auto_start_logging': True
        }
    def load(self):
        try:
            with open(self.path, 'r') as f:
                config = json.load(f)
                # デフォルト値にないキーを補完
                for key, value in self.defaults.items():
                    config.setdefault(key, value)
                return config
        except (FileNotFoundError, json.JSONDecodeError):
            return self.defaults.copy()
    def save(self, config):
        with open(self.path, 'w') as f:
            json.dump(config, f, indent=4)


class AppWindow(QMainWindow):
    logging_status_changed = pyqtSignal(bool, bool, str)
    log_message_received = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.just_switched_app = False
        storage_path = os.path.join(os.path.expanduser('~'), ".activity-logger")
        self.db_manager = DatabaseManager(os.path.join(storage_path, "activity.db"))

        self.config_manager = ConfigManager(os.path.join(storage_path, "config.json"))
        self.config = self.config_manager.load()
        
        self.event_manager = EventTapManager()

        self.setWindowTitle('Activity Logger')
        self.setGeometry(150, 150, 900, 700)
        self.setStyleSheet("QMainWindow { background-color: #f1f5f9; } QPushButton { font-size: 14px; }")

        central_widget = QWidget(self); self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget); main_layout.setContentsMargins(0,0,0,0); main_layout.setSpacing(0)

        nav_bar = QWidget(); nav_bar.setStyleSheet("background-color: #e2e8f0;"); nav_layout = QHBoxLayout(nav_bar); nav_layout.setContentsMargins(10, 5, 10, 5)
        

        self.dashboard_button = QPushButton("Dashboard")
        self.log_button = QPushButton("Live Log")
        self.settings_button = QPushButton("Settings")
        self.dashboard_button.clicked.connect(lambda: self.switch_view(0))
        self.log_button.clicked.connect(lambda: self.switch_view(1))
        self.settings_button.clicked.connect(lambda: self.switch_view(2))
        
        nav_layout.addWidget(self.dashboard_button); nav_layout.addWidget(self.log_button); nav_layout.addWidget(self.settings_button); nav_layout.addStretch()
        main_layout.addWidget(nav_bar)

        self.stacked_widget = QStackedWidget(); main_layout.addWidget(self.stacked_widget)
        
        dashboard_page = self.create_dashboard_page(); self.stacked_widget.addWidget(dashboard_page)
        log_page = self.create_log_page(); self.stacked_widget.addWidget(log_page)

        settings_page = self.create_settings_page(); self.stacked_widget.addWidget(settings_page)
        
        self.log_message_received.connect(self.update_gui_log_slot)
        self.switch_view(0)
        

        if self.config.get('auto_start_logging', True):
            QTimer.singleShot(500, self.start_logging)
    
    def create_dashboard_page(self) -> QWidget:

        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(20)
        title = QLabel("Today's Activity Summary"); title_font = QFont(); title_font.setPointSize(24); title_font.setBold(True); title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter); layout.addWidget(title)
        stats_layout = QHBoxLayout(); stats_layout.setSpacing(20)
        self.keystrokes_label_val = QLabel("Calculating..."); self.top_apps_label_val = QLabel("No data")
        stats_layout.addWidget(self.create_stat_card("Today's Total Keystrokes", self.keystrokes_label_val))
        stats_layout.addWidget(self.create_stat_card("Top 3 Most Used Apps", self.top_apps_label_val)); layout.addLayout(stats_layout)
        self.chart_view = QWebEngineView(); layout.addWidget(self.chart_view)
        return page

    def create_log_page(self) -> QWidget:

        page = QWidget(); layout = QVBoxLayout(page)
        self.log_text_edit = QTextEdit(); self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setFont(QFont("Monaco", 12)); self.log_text_edit.setStyleSheet("background-color: #ffffff; border: none; padding: 10px;")
        layout.addWidget(self.log_text_edit)
        return page
        

    def create_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page); layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(25)

        title = QLabel("Settings"); title_font = QFont(); title_font.setPointSize(24); title_font.setBold(True); title.setFont(title_font)
        layout.addWidget(title)
        

        self.auto_start_checkbox = QCheckBox("Start logging automatically on launch")
        self.auto_start_checkbox.setChecked(self.config.get('auto_start_logging', True))
        self.auto_start_checkbox.stateChanged.connect(self.save_settings)
        layout.addWidget(self.auto_start_checkbox)
        
        layout.addStretch(1)


        login_items_frame = QFrame(); login_items_frame.setFrameShape(QFrame.StyledPanel)
        login_items_layout = QVBoxLayout(login_items_frame)
        login_items_title = QLabel("How to run this app on computer startup:")
        login_items_title.setFont(QFont("sans-serif", 16, QFont.Bold))
        login_items_text = QLabel("1. Open System Settings > General > Login Items.\n2. Click the '+' button.\n3. Find and select 'ActivityLogger.app' in your Applications folder.")
        open_login_items_button = QPushButton("Open Login Items Settings...")
        open_login_items_button.clicked.connect(self.open_login_items)
        
        login_items_layout.addWidget(login_items_title); login_items_layout.addWidget(login_items_text); login_items_layout.addWidget(open_login_items_button, 0, Qt.AlignLeft)
        layout.addWidget(login_items_frame)
        
        layout.addStretch(2)
        return page
    

    def save_settings(self):
        self.config['auto_start_logging'] = self.auto_start_checkbox.isChecked()
        self.config_manager.save(self.config)

    def create_stat_card(self, title: str, value_label: QLabel) -> QFrame:

        frame = QFrame(); frame.setStyleSheet("background-color: white; border-radius: 8px;"); frame.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(frame); title_label = QLabel(title); title_label.setStyleSheet("color: #64748b; font-size: 14px;")
        value_label.setStyleSheet("color: #0f172a; font-size: 28px; font-weight: bold;"); value_label.setWordWrap(True)
        layout.addWidget(title_label); layout.addWidget(value_label)
        return frame

    def switch_view(self, index):
        self.stacked_widget.setCurrentIndex(index)
        style_active = "background-color: #ffffff; border: none; padding: 8px 12px; border-radius: 6px;"
        style_inactive = "background-color: transparent; border: none; padding: 8px 12px;"
        
        self.dashboard_button.setStyleSheet(style_inactive)
        self.log_button.setStyleSheet(style_inactive)
        self.settings_button.setStyleSheet(style_inactive)
        
        if index == 0:
            self.refresh_dashboard_data()
            self.dashboard_button.setStyleSheet(style_active)
        elif index == 1:
            self.log_button.setStyleSheet(style_active)
        elif index == 2:
            self.settings_button.setStyleSheet(style_active)

    def refresh_dashboard_data(self):

        today_str = _dt.date.today().isoformat()
        self.db_manager.cursor.execute("SELECT content FROM logs WHERE event_type = 'KEYSTROKE' AND date(timestamp) = ?", (today_str,))
        total_keys = sum(len(row[0]) for row in self.db_manager.cursor.fetchall() if not row[0].startswith('['))
        self.keystrokes_label_val.setText(f"{total_keys:,}")
        self.db_manager.cursor.execute("SELECT timestamp, content FROM logs WHERE event_type = 'APP_SWITCH' AND date(timestamp) = ? ORDER BY timestamp ASC", (today_str,))
        app_switches = self.db_manager.cursor.fetchall()
        app_durations = defaultdict(float)
        if len(app_switches) > 1:
            for i in range(len(app_switches) - 1):
                duration = (_dt.datetime.fromisoformat(app_switches[i+1][0]) - _dt.datetime.fromisoformat(app_switches[i][0])).total_seconds()
                app_durations[app_switches[i][1]] += duration
        sorted_apps = sorted(app_durations.items(), key=lambda item: item[1], reverse=True)
        top_apps_text = "".join([f"{i+1}. {app} ({int(dur/60)} min)<br>" for i, (app, dur) in enumerate(sorted_apps[:3])])
        self.top_apps_label_val.setText(top_apps_text or "No data available")
        self.update_chart(app_durations)
        
    def update_chart(self, app_durations: Dict[str, float]):

        labels = list(app_durations.keys()); data = list(app_durations.values())
        chart_html = f"""<html><head><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head><body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;"><canvas id="chart"></canvas><script>new Chart(document.getElementById('chart'), {{type: 'doughnut', data: {{ labels: {labels}, datasets: [{{ label: 'Time (seconds)', data: {data}, backgroundColor: ['#3b82f6','#ef4444','#10b981','#f97316','#8b5cf6','#eab308','#64748b'] }}] }}, options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'right' }} }} }} }});</script></body></html>"""
        self.chart_view.setHtml(chart_html)

    def start_logging(self):

        self.just_switched_app = False
        if self.event_manager.start():
            log_message = "🟢 Logging started..."; self.db_manager.add_log_entry('SYSTEM', 'START'); self.log_message_received.emit(f"{log_message}\n")
            status_msg = "Status: Logging Active"; self.logging_status_changed.emit(True, False, status_msg)
        else:
            self.show_accessibility_prompt()
            
    def stop_logging(self):
 
        flush_buffer(); self.event_manager.stop()
        log_message = "⏹ Logging stopped."; self.db_manager.add_log_entry('SYSTEM', 'STOP'); self.log_message_received.emit(f"\n{log_message}\n")
        status_msg = "Status: Idle"; self.logging_status_changed.emit(False, False, status_msg)
        
    def toggle_pause(self):

        if not self.event_manager.is_running(): return
        if self.event_manager.is_paused:
            self.event_manager.resume(); log_message = "▶️ Logging resumed."; event = "RESUME"; is_paused = False; status_msg = "Status: Logging Active"
        else:
            self.event_manager.pause(); log_message = "⏸️ Logging paused."; event = "PAUSE"; is_paused = True; status_msg = "Status: Paused"
        self.db_manager.add_log_entry('SYSTEM', event); self.log_message_received.emit(f"\n{log_message}\n");
        self.logging_status_changed.emit(True, is_paused, status_msg)
        
    def toggle_logging(self):

        if self.event_manager.is_running(): self.stop_logging()
        else: self.start_logging()
        
    def open_database_viewer(self):

        db_viewer_app = "DB Browser for SQLite.app"; db_viewer_path = os.path.join("/Applications", db_viewer_app); download_url = "https://sqlitebrowser.org/dl/"; db_file_path = self.db_manager.db_path
        if os.path.exists(db_viewer_path):
            try: subprocess.run(["open", "-a", db_viewer_path, db_file_path], check=True)
            except Exception as e: QMessageBox.critical(self, "Error", f"Could not open DB Viewer: {e}")
        else:
            if QMessageBox.question(self, "DB Viewer Not Found", "DB Browser for SQLite is recommended.\n\nOpen download page?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes: webbrowser.open(download_url)
    
    def show_accessibility_prompt(self):

        self.log_message_received.emit("❌ Logging failed: Accessibility permission required.\n")
        msg_box = QMessageBox(self); msg_box.setIcon(QMessageBox.Warning); msg_box.setText("<b>Permission Required</b>")
        msg_box.setInformativeText("To monitor keyboard input, this application needs 'Accessibility' permissions from macOS.\n\n<b>How to enable:</b>\n1. Click 'Open System Settings' below.\n2. Find 'ActivityLogger' in the list.\n3. Turn on the switch next to it.\n\nYou may need to restart the application after granting permission.")
        open_settings_button = msg_box.addButton("Open System Settings", QMessageBox.ActionRole)
        msg_box.addButton("Later", QMessageBox.RejectRole); msg_box.exec_()
        if msg_box.clickedButton() == open_settings_button:
            url_scheme = "x-apple.systempreferences:com.apple.preference.security&path=Privacy_Accessibility"
            subprocess.run(["open", url_scheme])

    def open_login_items(self):

        url_scheme = "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"
        subprocess.run(["open", url_scheme])

    def closeEvent(self, event):
        self.hide(); event.ignore()
        
    def update_gui_log_slot(self, log_text: str):
        if hasattr(self, 'log_text_edit'):
            self.log_text_edit.moveCursor(self.log_text_edit.textCursor().End); self.log_text_edit.insertPlainText(log_text)
        print(log_text, end='', flush=True)

    def show_window(self):
        self.show(); self.activateWindow(); self.raise_()
        self.switch_view(0)

def main() -> None:

    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    global window
    window = AppWindow()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Systray", "I couldn't detect any system tray on this system."); sys.exit(1)
    app.aboutToQuit.connect(window.db_manager.close)
    try:
        ICON_PATH = resource_path('asset/icon.svg')
        if not os.path.exists(ICON_PATH): raise FileNotFoundError(f"Icon path not found: {ICON_PATH}")
        with open(ICON_PATH, 'r', encoding='utf-8') as f: svg_template_string = f.read()
        COLOR_ACTIVE = "#007AFF"; COLOR_INACTIVE = "#8E8E93"
        icon_active = create_icon_from_svg(svg_template_string, COLOR_ACTIVE); icon_inactive = create_icon_from_svg(svg_template_string, COLOR_INACTIVE)
    except Exception as e:
        print(f"Icon setup error: {e}"); icon_active, icon_inactive = QIcon(), QIcon()
        
    tray_icon = QSystemTrayIcon(icon_inactive, parent=app); tray_icon.setToolTip("Activity Logger")
    
    menu = QMenu(); status_action = QAction("Status: Stopped", menu); status_action.setEnabled(False)
    toggle_log_action = QAction("Start Logging", menu); toggle_log_action.triggered.connect(window.toggle_logging)
    pause_action = QAction("Pause", menu); pause_action.triggered.connect(window.toggle_pause); pause_action.setEnabled(False)
    menu.addAction(status_action); menu.addSeparator(); menu.addAction(toggle_log_action); menu.addAction(pause_action); menu.addSeparator()
    
    show_window_action = QAction("Open Window...", menu); show_window_action.triggered.connect(window.show_window)
    menu.addAction(show_window_action)
    
    view_db_action = QAction("Open Database...", menu); view_db_action.triggered.connect(window.open_database_viewer); menu.addAction(view_db_action)
    
    menu.addSeparator(); quit_action = QAction("Quit", menu); quit_action.triggered.connect(app.quit); menu.addAction(quit_action)
    
    tray_icon.setContextMenu(menu); tray_icon.show()
    
    def update_tray_menu(is_logging, is_paused, status_message):
        status_action.setText(status_message)
        if not is_logging:
            tray_icon.setIcon(icon_inactive); toggle_log_action.setText("Start Logging"); pause_action.setEnabled(False)
            pause_action.setText("Pause")
        else:
            toggle_log_action.setText("Stop Logging")
            pause_action.setEnabled(True)
            if is_paused: tray_icon.setIcon(icon_inactive); pause_action.setText("Resume")
            else: tray_icon.setIcon(icon_active); pause_action.setText("Pause")

    window.logging_status_changed.connect(update_tray_menu)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
