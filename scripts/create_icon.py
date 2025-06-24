# build_icon.py (デバッグ用・中間ファイルを削除しない)

import sys
import os
import subprocess
import shutil

from PyQt5.QtWidgets import QApplication
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtCore import Qt, QSize

def create_icns_from_svg(svg_path, output_icns_path):
    """
    指定されたSVGファイルから、macOS用の.icnsファイルを生成する。
    """
    # 一時的な作業ディレクトリを作成
    iconset_dir = "temp.iconset"
    if os.path.exists(iconset_dir):
        shutil.rmtree(iconset_dir)
    os.makedirs(iconset_dir)

    print(f"作業ディレクトリ '{iconset_dir}' を作成しました。")

    # SVGファイルを読み込む
    with open(svg_path, 'r') as f:
        svg_data = f.read().encode('utf-8')

    # 必要なアイコンサイズ
    sizes = {
        "icon_16x16.png": 16, "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32, "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128, "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256, "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512, "icon_512x512@2x.png": 1024,
    }

    # PyQtアプリケーションのインスタンス（描画処理に必要）
    app = QApplication.instance() or QApplication(sys.argv)
    renderer = QSvgRenderer(svg_data)

    # 各サイズのPNG画像を生成
    for filename, size in sizes.items():
        pixmap = QPixmap(QSize(size, size))
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        output_path = os.path.join(iconset_dir, filename)
        pixmap.save(output_path, "PNG")
        print(f"'{output_path}' を生成しました。")

    # iconutilコマンドで.icnsファイルを生成
    print(f"'{iconset_dir}' から '{output_icns_path}' を生成します...")
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", iconset_dir, "-o", output_icns_path],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✅ .icnsファイルの生成に成功しました！")
    except subprocess.CalledProcessError as e:
        print("❌ .icnsファイルの生成に失敗しました。")
        print(f"エラー: {e.stderr}")
    finally:
        # --- MODIFIED: 確認のために一時ディレクトリを削除しない ---
        shutil.rmtree(iconset_dir)
        # print(f"デバッグのため、作業ディレクトリ '{iconset_dir}' を削除しませんでした。")
        # print("中身を確認後、手動で削除してください。")


if __name__ == "__main__":
    svg_file = os.path.join("asset", "icon.svg")
    icns_file = os.path.join("asset", "icon.icns")
    
    if not os.path.exists(svg_file):
        print(f"エラー: ソースファイル '{svg_file}' が見つかりません。")
    else:
        create_icns_from_svg(svg_file, icns_file)
