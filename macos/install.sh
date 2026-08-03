#!/usr/bin/env bash
#
# Clipboard AI — macOS otomatik kurulum
#
# Yaptıkları:
#   1. Homebrew yoksa kurar
#   2. Ollama yoksa kurar ve servisini başlatır
#   3. Modeli indirir (varsayılan: qwen2.5:7b)
#   4. İzole bir Python venv oluşturur, bağımlılıkları kurar
#   5. Oturum açılışında otomatik başlaması için LaunchAgent kurar
#   6. Uygulamayı hemen başlatır
#
# Kullanım:  ./install.sh
#   Model değiştirmek için:  OLLAMA_MODEL=llama3.1:8b ./install.sh
#
set -euo pipefail

# ── Sabitler ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Clipboard AI"
LABEL="com.ollama.clipboardai"
SUPPORT_DIR="$HOME/Library/Application Support/ollama-clipboard"
INSTALL_DIR="$SUPPORT_DIR/app"
VENV_DIR="$SUPPORT_DIR/venv"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"

log()  { printf '\033[1;32m[✓]\033[0m %s\n' "$*"; }
info() { printf '\033[1;34m[»]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[✗]\033[0m %s\n' "$*" >&2; exit 1; }

echo "==============================================="
echo "   $APP_NAME — macOS Kurulum"
echo "==============================================="
echo

[[ "$(uname)" == "Darwin" ]] || die "Bu betik yalnızca macOS içindir."

# ── 1. Homebrew ─────────────────────────────────────────────────────────────
if ! command -v brew >/dev/null 2>&1; then
    info "Homebrew bulunamadı, kuruluyor…"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Apple Silicon / Intel için brew'i PATH'e al
    if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
else
    log "Homebrew mevcut."
fi

# ── 2. Ollama ───────────────────────────────────────────────────────────────
if ! command -v ollama >/dev/null 2>&1; then
    info "Ollama bulunamadı, kuruluyor…"
    brew install ollama
else
    log "Ollama mevcut."
fi

info "Ollama servisi başlatılıyor…"
brew services start ollama >/dev/null 2>&1 || ollama serve >/dev/null 2>&1 &
# Ollama API'nin ayağa kalkmasını bekle (en fazla ~30 sn)
for _ in $(seq 1 30); do
    if curl -fsS http://localhost:11434/api/version >/dev/null 2>&1; then break; fi
    sleep 1
done
curl -fsS http://localhost:11434/api/version >/dev/null 2>&1 \
    && log "Ollama çalışıyor." \
    || warn "Ollama API'ye ulaşılamadı; model indirme başarısız olabilir."

# ── 3. Model ────────────────────────────────────────────────────────────────
if ollama list 2>/dev/null | grep -q "${MODEL%%:*}"; then
    log "Model zaten var: $MODEL"
else
    info "Model indiriliyor ($MODEL) — boyuta göre birkaç dakika sürebilir…"
    ollama pull "$MODEL" || warn "Model indirilemedi; sonra 'ollama pull $MODEL' deneyin."
fi

# ── 4. Uygulama dosyaları + Python venv ─────────────────────────────────────
info "Uygulama dosyaları kopyalanıyor…"
mkdir -p "$INSTALL_DIR"
cp "$SCRIPT_DIR/clipboard_ai_mac.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements-mac.txt" "$INSTALL_DIR/"

PYTHON_BIN="$(command -v python3)"
[[ -n "$PYTHON_BIN" ]] || die "python3 bulunamadı. 'brew install python' deneyin."

info "Python sanal ortamı kuruluyor…"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip --quiet
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements-mac.txt" --quiet
log "Bağımlılıklar kuruldu."

# ── 5. LaunchAgent (oturum açılışında otomatik başlat) ──────────────────────
info "LaunchAgent kuruluyor…"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_DIR/bin/python</string>
        <string>$INSTALL_DIR/clipboard_ai_mac.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
    <key>StandardOutPath</key>
    <string>$SUPPORT_DIR/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$SUPPORT_DIR/launchd.err.log</string>
</dict>
</plist>
PLIST

# Eski oturum varsa kaldır, yenisini yükle → hemen başlar (RunAtLoad)
launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH"
log "Otomatik başlatma kuruldu ve uygulama başlatıldı."

# ── 6. Bilgilendirme ────────────────────────────────────────────────────────
echo
echo "==============================================="
log  "Kurulum tamamlandı!"
echo "==============================================="
echo
echo "  • Menü çubuğunda 🟢 simgesini göreceksiniz."
echo "  • Kullanım: başına '?' koyduğunuz bir metni kopyalayın —"
echo "    cevap panoya yazılır, Cmd+V ile yapıştırın."
echo "  • Hızlı soru kısayolu: Cmd+Alt+Space"
echo
warn "ÖNEMLİ — Erişilebilirlik izni:"
echo "    Kısayol ve 'görünmeden yazma' için macOS izni gerekir:"
echo "    Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik"
echo "    listesine venv python'u ekleyip açın:"
echo "    $VENV_DIR/bin/python"
echo
echo "  Ayar dosyası: $SUPPORT_DIR/config.json"
echo "  Kaldırmak için: ./uninstall.sh"
echo
