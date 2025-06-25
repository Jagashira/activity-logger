# app/utils.py
import sys
import os
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt, QByteArray
from PyQt5.QtSvg import QSvgRenderer

def resource_path(relative_path):
    """アセットへの絶対パスを取得する。開発時とPyInstaller実行時の両方で動作する。"""
    try:
        base_path = sys._MEIPASS
    except Exception:

        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    return os.path.join(base_path, relative_path)

def create_icon_from_svg(svg_template: str, color: str | QColor, size: int = 32) -> QIcon:

    svg_data = svg_template.replace('#000000', color)
    svg_bytes = QByteArray(svg_data.encode('utf-8'))
    renderer = QSvgRenderer(svg_bytes)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
