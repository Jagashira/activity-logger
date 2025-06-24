#!/bin/bash

# このスクリプトは、macOSアプリケーションのビルドプロセスを自動化します。
# エラーが発生した時点でスクリプトを停止するように設定します。
set -e

echo "------------------------------------"
echo "ビルドプロセスを開始します..."
echo "------------------------------------"

# ステップ1: 古いビルドファイルをクリーンアップ
echo "[1/4] 古いビルドファイル (build/, dist/) を削除しています..."
rm -rf build/
rm -rf dist/
echo "クリーンアップ完了。"
echo ""

# ステップ2: logger.spec ファイルの確認と生成
echo "[2/4] logger.spec ファイルを確認しています..."
if [ ! -f "logger.spec" ]; then
    echo "logger.spec が見つかりません。正しい内容で新規作成します..."
    # pyi-makespecは不完全なファイルを生成するため、
    # 既知の正しい設定を直接書き込みます。
    cat > logger.spec << EOF
# -*- mode: python ; coding: utf-8 -*-


# --- ステップ1: スクリプトと依存関係の解析 ---
a = Analysis(
    ['scripts/logger.py'],
    pathex=[],
    binaries=[],
    datas=[('asset/icon.svg', 'asset')],
    hiddenimports=['objc', 'sqlite3', 'pyminizip'],
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
        'LSUIElement': '1'  # Dockにアイコンを表示しない設定
    },
)


EOF
    echo "logger.spec を作成しました。"
else
    echo "既存の logger.spec を使用します。"
fi
echo ""

# ステップ3: アプリアイコン (.icns) を作成
CREATE_ICON_SCRIPT="scripts/create_icon.py"
if [ ! -f "$CREATE_ICON_SCRIPT" ]; then
    echo "エラー: $CREATE_ICON_SCRIPT が見つかりません。アイコンを生成できません。"
    exit 1
fi
echo "[3/4] アプリアイコン (asset/icon.icns) を生成しています..."
python "$CREATE_ICON_SCRIPT"
echo "アイコン生成完了。"
echo ""

# ステップ4: PyInstallerでアプリケーションをビルド
echo "[4/4] PyInstallerでアプリケーションをビルドしています..."
python -m PyInstaller logger.spec

echo ""
echo "------------------------------------"
echo "✅ ビルドプロセスが正常に完了しました！"
echo "dist/ActivityLogger.app を確認してください。"
echo "------------------------------------"
