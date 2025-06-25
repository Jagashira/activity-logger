#!/bin/bash

echo "------------------------------------"
echo "ビルドプロセスを開始します..."
echo "------------------------------------"


echo "[1/4] 古いビルドファイル (build/, dist/) を削除しています..."
rm -rf build/
rm -rf dist/
echo "クリーンアップ完了。"
echo ""


echo "[2/4] logger.spec ファイルを確認しています..."
if [ ! -f "logger.spec" ]; then
    echo "logger.spec が見つかりません。正しい内容で新規作成します..."
    cat > logger.spec << EOF
# -*- mode: python ; coding: utf-8 -*-

# --- ステップ1: スクリプトと依存関係の解析 ---
a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=[],
    datas=[('asset/icon.svg', 'asset')],
    hiddenimports=['objc', 'sqlite3', 'pyminizip','PyQt5.QtWebEngineWidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=None,
)

# --- ステップ2: Pythonライブラリの圧縮 ---
pyz = PYZ(a.pure)

# --- ステップ3: 実行ファイルの作成 ---
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ActivityLogger',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# --- ステップ4: 全てのファイルをまとめる ---
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ActivityLogger',
)

# --- ステップ5: .appバンドルの作成 ---
app = BUNDLE(
    coll,
    name='ActivityLogger.app',
    icon='asset/icon.icns',
    bundle_identifier=None,
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'LSUIElement': '1'
    },
)


EOF
    echo "logger.spec を作成しました。"
else
    echo "既存の logger.spec を使用します。"
fi
echo ""


CREATE_ICON_SCRIPT="scripts/create_icon.py"
if [ ! -f "$CREATE_ICON_SCRIPT" ]; then
    echo "エラー: $CREATE_ICON_SCRIPT が見つかりません。アイコンを生成できません。"
    exit 1
fi
echo "[3/4] アプリアイコン (asset/icon.icns) を生成しています..."
python "$CREATE_ICON_SCRIPT"
echo "アイコン生成完了。"
echo ""


echo "[4/4] PyInstallerでアプリケーションをビルドしています..."
python -m PyInstaller logger.spec

echo ""
echo "------------------------------------"
echo "✅ ビルドプロセスが正常に完了しました！"
echo "dist/ActivityLogger.app を確認してください。"
echo "------------------------------------"
