from __future__ import annotations
import ctypes
import datetime as _dt
import signal
import sys
from typing import List
import os
import time

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
# --- MODIFIED: SVG関連のモジュールをインポート ---
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import QTimer, pyqtSignal, Qt, QByteArray
from PyQt5.QtSvg import QSvgRenderer

# (グローバル変数とコールバック関数、AppObserver, EventTapManager, AppWindow のコードは変更なしなので省略)
# (For brevity, the unchanged classes AppObserver, EventTapManager, and AppWindow are omitted here.)
_buffer: List[str] = []
window: AppWindow = None
def flush_buffer() -> None:
    if not (_buffer and window): return
    if window.just_switched_app:
        log_text = f"\n\u3000{''.join(_buffer)}"
        window.just_switched_app = False
    else: log_text = ''.join(_buffer)
    window.update_log(log_text); _buffer.clear()
def keyboard_cb(proxy, etype, event, refcon):
    if etype != kCGEventKeyDown: return event
    _, text = CGEventKeyboardGetUnicodeString(event, 1, None, None)
    keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
    if keycode in (36, 76, 52):
        flush_buffer()
        if window: window.update_log("\n")
    elif keycode == 51:
        if _buffer: _buffer.pop()
        else:
            if window: window.update_log("[<-]")
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
                window.update_log(f"\n🗂️  APP  {app}  ({stamp})")
                window.just_switched_app = True
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
        self.autosave_dir = os.path.join(os.path.expanduser('~'),"logs"); self.autosave_filepath = None; self.max_log_size_bytes = 0; self.current_log_file = None; self.just_switched_app = False
        self.setWindowTitle('Activity Logger'); self.setGeometry(100, 100, 700, 550); self.text_edit = QTextEdit(self); self.text_edit.setReadOnly(True)
        self.toggle_button = QPushButton('Start Logging', self); self.clear_button = QPushButton('Clear Log', self); self.save_button = QPushButton('Save Log Now', self); self.zip_button = QPushButton('Save & Zip Log Now', self)
        button_layout = QHBoxLayout(); button_layout.addWidget(self.toggle_button); button_layout.addWidget(self.clear_button); button_layout.addStretch(1); button_layout.addWidget(self.save_button); button_layout.addWidget(self.zip_button)
        autosave_layout = QHBoxLayout(); self.autosave_checkbox = QCheckBox("Auto-save log", self); self.autosave_checkbox.setChecked(True); autosave_layout.addWidget(self.autosave_checkbox)
        autosave_layout.addWidget(QLabel("Max Size (KB):", self)); self.autosave_size_spinbox = QSpinBox(self); self.autosave_size_spinbox.setRange(100, 10000); self.autosave_size_spinbox.setValue(1024)
        autosave_layout.addWidget(self.autosave_size_spinbox); autosave_layout.addStretch(1); main_layout = QVBoxLayout(); main_layout.addWidget(self.text_edit); main_layout.addLayout(button_layout); main_layout.addLayout(autosave_layout)
        container = QWidget(); container.setLayout(main_layout); self.setCentralWidget(container)
        self.statusBar = QStatusBar(self); self.setStatusBar(self.statusBar)
        self.event_manager = EventTapManager()
        self.update_status("Ready. Start logging from the menu bar icon or this window.")
        self.toggle_button.clicked.connect(self.toggle_logging); self.save_button.clicked.connect(self.save_log_file); self.zip_button.clicked.connect(self.save_zip_file); self.clear_button.clicked.connect(self.text_edit.clear)
    def rotate_log_file(self):
        if self.current_log_file: self.current_log_file.close()
        start_time = _dt.datetime.now().strftime("%Y%m%d_%H%M%S"); filename = f"auto_log_{start_time}.txt"; self.autosave_filepath = os.path.join(self.autosave_dir, filename)
        try:
            self.current_log_file = open(self.autosave_filepath, 'a', encoding='utf-8')
            status_msg = f"Logging to new file: {filename}"; self.update_status(status_msg); self.logging_status_changed.emit(True, False, status_msg)
        except Exception as e: self.update_status(f"Error opening new log file: {e}"); self.current_log_file = None
    def start_logging(self):
        self.just_switched_app = False
        if self.autosave_checkbox.isChecked():
            try: os.makedirs(self.autosave_dir, exist_ok=True)
            except OSError as e: QMessageBox.critical(self, "Auto-save Error", f"Could not create directory:\n{self.autosave_dir}\n\nError: {e}"); return
            self.max_log_size_bytes = self.autosave_size_spinbox.value() * 1024; self.rotate_log_file()
        if self.event_manager.start():
            self.update_log("🟢 Logging started...\n"); status_msg = "Status: Logging Active"; self.update_status(status_msg)
            self.toggle_button.setText("Stop Logging"); self.set_settings_enabled(False); self.logging_status_changed.emit(True, False, status_msg)
        else: self.update_log("❌ FAILED TO CREATE EVENT TAP...\n")
    def stop_logging(self):
        if self.current_log_file:
            self.current_log_file.close(); self.current_log_file = None; status_msg = "Final log saved. Status: Idle."
        else: status_msg = "Status: Idle"
        self.autosave_filepath = None; flush_buffer(); self.event_manager.stop(); self.update_log("\n⏹ Logging stopped.\n"); self.update_status(status_msg)
        self.toggle_button.setText("Start Logging"); self.set_settings_enabled(True); self.logging_status_changed.emit(False, False, status_msg)
    def toggle_pause(self):
        if not self.event_manager.is_running(): return
        if self.event_manager.is_paused:
            self.event_manager.resume(); self.update_log("\n▶️ Logging resumed.\n"); status_msg = "Status: Logging Active"; self.update_status(status_msg)
            self.logging_status_changed.emit(True, False, status_msg)
        else:
            self.event_manager.pause(); self.update_log("\n⏸️ Logging paused.\n"); status_msg = "Status: Paused"; self.update_status(status_msg)
            self.logging_status_changed.emit(True, True, status_msg)
    def set_settings_enabled(self, enabled: bool): self.autosave_checkbox.setEnabled(enabled); self.autosave_size_spinbox.setEnabled(enabled); self.save_button.setEnabled(enabled); self.zip_button.setEnabled(enabled); self.clear_button.setEnabled(enabled)
    def toggle_logging(self):
        if self.event_manager.is_running(): self.stop_logging()
        else: self.start_logging()
    def closeEvent(self, event): self.hide(); event.ignore()
    def update_status(self, message: str): self.statusBar.showMessage(message)
    def update_log(self, log_text: str):
        self.text_edit.moveCursor(self.text_edit.textCursor().End); self.text_edit.insertPlainText(log_text); print(log_text, end='', flush=True)
        if self.autosave_checkbox.isChecked() and self.current_log_file:
            try:
                self.current_log_file.write(log_text); self.current_log_file.flush()
                if os.path.getsize(self.autosave_filepath) > self.max_log_size_bytes: self.rotate_log_file()
            except Exception as e: self.update_status(f"Error writing to log file: {e}")
    def save_log_file(self):
        log_content = self.text_edit.toPlainText();
        if not log_content: self.update_status("Log is empty. Nothing to save."); return
        default_filename = f"manual_save_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"; path, _ = QFileDialog.getSaveFileName(self, "Save Log File", default_filename, "Text Files (*.txt);;All Files (*)")
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f: f.write(log_content)
                self.update_status(f"Log saved to {os.path.basename(path)}")
            except Exception as e: self.update_status(f"Error saving file: {e}")
    def save_zip_file(self):
        log_content = self.text_edit.toPlainText();
        if not log_content: self.update_status("Log is empty. Nothing to save."); return
        password, ok = QInputDialog.getText(self, "Set Zip Password", "Enter a password for the archive:", QLineEdit.Password)
        if not (ok and password): self.update_status("Zip save cancelled. Password is required."); return
        default_filename = f"manual_save_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"; zip_path, _ = QFileDialog.getSaveFileName(self, "Save Zipped Log File", default_filename, "Zip Archives (*.zip)")
        if zip_path:
            temp_txt_file = "temp_log_for_zip.txt"
            try:
                with open(temp_txt_file, "w", encoding='utf-8') as f: f.write(log_content)
                pyminizip.compress(temp_txt_file, None, zip_path, password, 9)
                self.update_status(f"Log zipped and saved to {os.path.basename(zip_path)}")
            except Exception as e: self.update_status(f"Error creating zip file: {e}")
            finally:
                if os.path.exists(temp_txt_file): os.remove(temp_txt_file)

# --- NEW: SVGデータを読み込み、色付けしてアイコンを生成するヘルパー関数 ---
def create_icon_from_svg(svg_template: str, color: str, size: int = 32) -> QIcon:
    """
    SVGテンプレートのテキストを読み込み、特定の色で描画したQIconを生成する。
    """
    # 色のプレースホルダーを置換
    svg_data = svg_template.replace('#000000', color)
    
    # SVGデータをバイト配列に変換
    svg_bytes = QByteArray(svg_data.encode('utf-8'))
    
    # SVGレンダラーを作成
    renderer = QSvgRenderer(svg_bytes)
    
    # 描画先のPixmapを作成
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent) # 背景を透明にする
    
    # PixmapにSVGを描画
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    
    return QIcon(pixmap)

# --- Main ---
def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    global window
    window = AppWindow()
    
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Systray", "I couldn't detect any system tray on this system.")
        sys.exit(1)

    # --- MODIFIED: SVGベースのアイコン生成ロジック ---
    try:
        script_path = os.path.abspath(__file__)
        script_dir = os.path.dirname(script_path)
        project_root = os.path.dirname(script_dir)
        ICON_PATH = os.path.join(project_root, 'asset', 'icon.svg')

        if not os.path.exists(ICON_PATH):
            raise FileNotFoundError(f"Icon not found at specified path: {ICON_PATH}")

        # SVGファイルを一度だけ読み込む
        with open(ICON_PATH, 'r', encoding='utf-8') as f:
            svg_template_string = f.read()

        COLOR_ACTIVE = "#007AFF"
        COLOR_INACTIVE = "#8E8E93"
        
        # テンプレートから色付きのアイコンを生成
        icon_active = create_icon_from_svg(svg_template_string, COLOR_ACTIVE)
        icon_inactive = create_icon_from_svg(svg_template_string, COLOR_INACTIVE)
        
    except Exception as e:
        print(f"Error setting up icons: {e}")
        QMessageBox.warning(None, "Icon Error", f"Could not load icon.\n\nError: {e}")
        icon_active, icon_inactive = QIcon(), QIcon()
        
    tray_icon = QSystemTrayIcon(icon_inactive, parent=app)
    tray_icon.setToolTip("Activity Logger")
    
    menu = QMenu(); status_action = QAction("ステータス: 停止中", menu); status_action.setEnabled(False)
    toggle_log_action = QAction("ロギング開始", menu); toggle_log_action.triggered.connect(window.toggle_logging)
    pause_action = QAction("一時停止", menu); pause_action.triggered.connect(window.toggle_pause); pause_action.setEnabled(False)
    show_action = QAction("ウィンドウを表示/隠す", menu); show_action.triggered.connect(lambda: window.show() if window.isHidden() else window.hide())
    quit_action = QAction("終了", menu); quit_action.triggered.connect(app.quit)
    menu.addAction(status_action); menu.addSeparator(); menu.addAction(toggle_log_action); menu.addAction(pause_action); menu.addAction(show_action); menu.addSeparator(); menu.addAction(quit_action)
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