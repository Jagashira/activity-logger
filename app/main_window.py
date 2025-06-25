# app/main_window.py
from __future__ import annotations
from typing import Dict
import datetime as _dt
import os
import webbrowser
import subprocess
from collections import defaultdict

from PyQt5.QtWidgets import (
    QMainWindow, QTextEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QMessageBox, QLabel, QFrame, QStackedWidget, QCheckBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWebEngineWidgets import QWebEngineView

from .database import DatabaseManager
from .config import ConfigManager
from .event_monitor import EventTapManager

class AppWindow(QMainWindow):
    logging_status_changed = pyqtSignal(bool, bool, str)

    def __init__(self, db_manager: DatabaseManager, config_manager: ConfigManager, event_manager: EventTapManager):
        super().__init__()
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.config = self.config_manager.load()
        self.event_manager = event_manager

        self.setWindowTitle('Activity Logger')
        self.setGeometry(150, 150, 900, 700)
        self.setStyleSheet("QMainWindow { background-color: #f1f5f9; } QPushButton { font-size: 14px; }")

        # Connect event monitor signals to this window's slots
        self.event_manager.log_event_received.connect(self.db_manager.add_log_entry)
        self.event_manager.gui_log_received.connect(self.update_gui_log_slot)

        self.init_ui()
        
        if self.config.get('auto_start_logging', True):
            self.start_logging()

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)

        nav_bar = QWidget(); nav_bar.setStyleSheet("background-color: #e2e8f0;");
        nav_layout = QHBoxLayout(nav_bar); nav_layout.setContentsMargins(10, 5, 10, 5)
        
        self.dashboard_button = QPushButton("Dashboard")
        self.log_button = QPushButton("Live Log")
        self.settings_button = QPushButton("Settings")
        self.dashboard_button.clicked.connect(lambda: self.switch_view(0))
        self.log_button.clicked.connect(lambda: self.switch_view(1))
        self.settings_button.clicked.connect(lambda: self.switch_view(2))
        
        nav_layout.addWidget(self.dashboard_button); nav_layout.addWidget(self.log_button)
        nav_layout.addWidget(self.settings_button); nav_layout.addStretch()
        main_layout.addWidget(nav_bar)

        self.stacked_widget = QStackedWidget(); main_layout.addWidget(self.stacked_widget)
        
        self.stacked_widget.addWidget(self.create_dashboard_page())
        self.stacked_widget.addWidget(self.create_log_page())
        self.stacked_widget.addWidget(self.create_settings_page())
        
        self.switch_view(0)


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
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 30, 30, 30); layout.setSpacing(25)
        title = QLabel("Settings"); title_font = QFont(); title_font.setPointSize(24); title_font.setBold(True); title.setFont(title_font); layout.addWidget(title)
        self.auto_start_checkbox = QCheckBox("Start logging automatically on launch"); self.auto_start_checkbox.setChecked(self.config.get('auto_start_logging', True))
        self.auto_start_checkbox.stateChanged.connect(self.save_settings); layout.addWidget(self.auto_start_checkbox); layout.addStretch(1)
        login_items_frame = QFrame(); login_items_frame.setFrameShape(QFrame.StyledPanel); login_items_layout = QVBoxLayout(login_items_frame)
        login_items_title = QLabel("How to run this app on computer startup:"); login_items_title.setFont(QFont("sans-serif", 16, QFont.Bold))
        login_items_text = QLabel("1. Open System Settings > General > Login Items.\n2. Click the '+' button.\n3. Find and select 'ActivityLogger.app' in your Applications folder.")
        open_login_items_button = QPushButton("Open Login Items Settings..."); open_login_items_button.clicked.connect(self.open_login_items)
        login_items_layout.addWidget(login_items_title); login_items_layout.addWidget(login_items_text); login_items_layout.addWidget(open_login_items_button, 0, Qt.AlignLeft); layout.addWidget(login_items_frame); layout.addStretch(2)
        return page
    def create_stat_card(self, title: str, value_label: QLabel) -> QFrame:
        frame = QFrame(); frame.setStyleSheet("background-color: white; border-radius: 8px;"); frame.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(frame); title_label = QLabel(title); title_label.setStyleSheet("color: #64748b; font-size: 14px;")
        value_label.setStyleSheet("color: #0f172a; font-size: 28px; font-weight: bold;"); value_label.setWordWrap(True); layout.addWidget(title_label); layout.addWidget(value_label)
        return frame
    def switch_view(self, index):
        self.stacked_widget.setCurrentIndex(index); style_active = "background-color: #ffffff; border: none; padding: 8px 12px; border-radius: 6px;"; style_inactive = "background-color: transparent; border: none; padding: 8px 12px;"
        self.dashboard_button.setStyleSheet(style_inactive); self.log_button.setStyleSheet(style_inactive); self.settings_button.setStyleSheet(style_inactive)
        if index == 0: self.refresh_dashboard_data(); self.dashboard_button.setStyleSheet(style_active)
        elif index == 1: self.log_button.setStyleSheet(style_active)
        elif index == 2: self.settings_button.setStyleSheet(style_active)
    def refresh_dashboard_data(self):
        today_str = _dt.date.today().isoformat()
        self.db_manager.cursor.execute("SELECT content FROM logs WHERE event_type = 'KEYSTROKE' AND date(timestamp) = ?", (today_str,))
        total_keys = sum(len(row[0]) for row in self.db_manager.cursor.fetchall() if not row[0].startswith('[')); self.keystrokes_label_val.setText(f"{total_keys:,}")
        self.db_manager.cursor.execute("SELECT timestamp, content FROM logs WHERE event_type = 'APP_SWITCH' AND date(timestamp) = ? ORDER BY timestamp ASC", (today_str,))
        app_switches = self.db_manager.cursor.fetchall(); app_durations = defaultdict(float)
        if len(app_switches) > 1:
            for i in range(len(app_switches) - 1):
                duration = (_dt.datetime.fromisoformat(app_switches[i+1][0]) - _dt.datetime.fromisoformat(app_switches[i][0])).total_seconds()
                app_durations[app_switches[i][1]] += duration
        sorted_apps = sorted(app_durations.items(), key=lambda item: item[1], reverse=True)
        top_apps_text = "".join([f"{i+1}. {app} ({int(dur/60)} min)<br>" for i, (app, dur) in enumerate(sorted_apps[:3])]); self.top_apps_label_val.setText(top_apps_text or "No data available")
        self.update_chart(app_durations)
    def update_chart(self, app_durations: Dict[str, float]):
        labels = list(app_durations.keys()); data = list(app_durations.values())
        chart_html = f"""<html><head><script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head><body style="display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;"><canvas id="chart"></canvas><script>new Chart(document.getElementById('chart'), {{type: 'doughnut', data: {{ labels: {labels}, datasets: [{{ label: 'Time (seconds)', data: {data}, backgroundColor: ['#3b82f6','#ef4444','#10b981','#f97316','#8b5cf6','#eab308','#64748b'] }}] }}, options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'right' }} }} }} }});</script></body></html>"""
        self.chart_view.setHtml(chart_html)

    def start_logging(self):
        if self.event_manager.start():
            status_msg = "Status: Logging Active"; self.logging_status_changed.emit(True, False, status_msg)
            self.event_manager.log_event_received.emit('SYSTEM', 'START'); self.event_manager.gui_log_received.emit("🟢 Logging started...\n")
        else: self.show_accessibility_prompt()

    def stop_logging(self):
        self.event_manager.stop()
        status_msg = "Status: Idle"; self.logging_status_changed.emit(False, False, status_msg)
        self.event_manager.log_event_received.emit('SYSTEM', 'STOP'); self.event_manager.gui_log_received.emit("\n⏹ Logging stopped.\n")

    def toggle_pause(self):
        if not self.event_manager.is_running(): return
        if self.event_manager.is_paused:
            self.event_manager.resume(); event = "RESUME"; is_paused = False; status_msg = "Status: Logging Active"
            self.event_manager.gui_log_received.emit("\n▶️ Logging resumed.\n")
        else:
            self.event_manager.pause(); event = "PAUSE"; is_paused = True; status_msg = "Status: Paused"
            self.event_manager.gui_log_received.emit("\n⏸️ Logging paused.\n")
        self.event_manager.log_event_received.emit('SYSTEM', event)
        self.logging_status_changed.emit(True, is_paused, status_msg)

    def save_settings(self):
        self.config['auto_start_logging'] = self.auto_start_checkbox.isChecked()
        self.config_manager.save(self.config)

    def open_login_items(self):
        url_scheme = "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"
        subprocess.run(["open", url_scheme])

    def open_database_viewer(self):
        db_viewer_app = "DB Browser for SQLite.app"; db_viewer_path = os.path.join("/Applications", db_viewer_app); download_url = "https://sqlitebrowser.org/dl/"; db_file_path = self.db_manager.db_path
        if os.path.exists(db_viewer_path):
            try: subprocess.run(["open", "-a", db_viewer_path, db_file_path], check=True)
            except Exception as e: QMessageBox.critical(self, "Error", f"Could not open DB Viewer: {e}")
        else:
            if QMessageBox.question(self, "DB Viewer Not Found", "DB Browser for SQLite is recommended.\n\nOpen download page?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes: webbrowser.open(download_url)

    def show_accessibility_prompt(self):
        self.event_manager.gui_log_received.emit("❌ Logging failed: Accessibility permission required.\n")
        msg_box = QMessageBox(self); msg_box.setIcon(QMessageBox.Warning); msg_box.setText("<b>Permission Required</b>")
        msg_box.setInformativeText("To monitor keyboard input, this application needs 'Accessibility' permissions from macOS.\n\n<b>How to enable:</b>\n1. Click 'Open System Settings' below.\n2. Find 'ActivityLogger' in the list.\n3. Turn on the switch next to it.\n\nYou may need to restart the application after granting permission.")
        open_settings_button = msg_box.addButton("Open System Settings", QMessageBox.ActionRole)
        msg_box.addButton("Later", QMessageBox.RejectRole); msg_box.exec_()
        if msg_box.clickedButton() == open_settings_button:
            url_scheme = "x-apple.systempreferences:com.apple.preference.security&path=Privacy_Accessibility"
            subprocess.run(["open", url_scheme])

    def update_gui_log_slot(self, log_text: str):
        if hasattr(self, 'log_text_edit'):
            self.log_text_edit.moveCursor(self.log_text_edit.textCursor().End)
            self.log_text_edit.insertPlainText(log_text)
        print(log_text, end='', flush=True)

    def closeEvent(self, event):
        self.hide(); event.ignore()
