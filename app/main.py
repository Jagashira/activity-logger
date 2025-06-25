# app/main.py
import sys
import signal
import os

from PyQt5.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon, QAction, QMenu
from PyQt5.QtGui import QIcon

from .main_window import AppWindow
from .database import DatabaseManager
from .config import ConfigManager
from .event_monitor import EventTapManager
from .utils import resource_path, create_icon_from_svg

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)


    storage_path = os.path.join(os.path.expanduser('~'), ".activity-logger")
    db_manager = DatabaseManager(os.path.join(storage_path, "activity.db"))
    config_manager = ConfigManager(os.path.join(storage_path, "config.json"))
    event_manager = EventTapManager()
    

    window = AppWindow(db_manager, config_manager, event_manager)


    app.aboutToQuit.connect(db_manager.close)
    
 
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Systray", "System tray not available.")
        sys.exit(1)
    
    try:
        ICON_PATH = resource_path('asset/icon.svg')
        with open(ICON_PATH, 'r', encoding='utf-8') as f:
            svg_template_string = f.read()
        COLOR_ACTIVE = "#007AFF"; COLOR_INACTIVE = "#8E8E93"
        icon_active = create_icon_from_svg(svg_template_string, COLOR_ACTIVE)
        icon_inactive = create_icon_from_svg(svg_template_string, COLOR_INACTIVE)
    except Exception as e:
        print(f"Icon setup error: {e}"); icon_active, icon_inactive = QIcon(), QIcon()
        
    tray_icon = QSystemTrayIcon(icon_inactive, parent=app)
    tray_icon.setToolTip("Activity Logger")

    menu = QMenu()
    status_action = QAction("Status: Stopped", menu); status_action.setEnabled(False)
    toggle_log_action = QAction("Start Logging", menu); toggle_log_action.triggered.connect(window.start_logging)
    pause_action = QAction("Pause", menu); pause_action.triggered.connect(window.toggle_pause); pause_action.setEnabled(False)
    menu.addAction(status_action); menu.addSeparator(); menu.addAction(toggle_log_action); menu.addAction(pause_action); menu.addSeparator()
    
    show_window_action = QAction("Open Window...", menu); show_window_action.triggered.connect(window.show)
    menu.addAction(show_window_action)
    view_db_action = QAction("Open Database...", menu); view_db_action.triggered.connect(window.open_database_viewer); menu.addAction(view_db_action)
    menu.addSeparator(); quit_action = QAction("Quit", menu); quit_action.triggered.connect(app.quit); menu.addAction(quit_action)
    
    tray_icon.setContextMenu(menu)
    tray_icon.show()
    

    def update_tray_menu(is_logging, is_paused, status_message):
        status_action.setText(status_message)
        toggle_log_action.setText("Stop Logging" if is_logging else "Start Logging")
        pause_action.setEnabled(is_logging)
        if is_logging:
            if is_paused:
                tray_icon.setIcon(icon_inactive); pause_action.setText("Resume")
            else:
                tray_icon.setIcon(icon_active); pause_action.setText("Pause")
        else:
            tray_icon.setIcon(icon_inactive); pause_action.setText("Pause")

    window.logging_status_changed.connect(update_tray_menu)

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
