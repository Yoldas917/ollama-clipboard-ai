#!/usr/bin/env bash
#
# Clipboard AI — macOS kaldırma
#
set -euo pipefail

LABEL="com.ollama.clipboardai"
SUPPORT_DIR="$HOME/Library/Application Support/ollama-clipboard"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "Clipboard AI kaldırılıyor…"

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
pkill -f "clipboard_ai_mac.py" >/dev/null 2>&1 || true

read -r -p "Ayarları ve logları da silelim mi? ($SUPPORT_DIR) [e/H] " ans
if [[ "${ans:-H}" =~ ^[eE]$ ]]; then
    rm -rf "$SUPPORT_DIR"
    echo "Tüm dosyalar silindi."
else
    echo "Uygulama durduruldu; ayarlar korundu."
fi

echo "Not: Ollama ve indirdiğiniz modeller silinmedi."
echo "İsterseniz: brew services stop ollama && brew uninstall ollama"
