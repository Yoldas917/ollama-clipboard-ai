# Clipboard AI

Ollama ile çalışan pano (clipboard) yapay zekâ asistanı. Başına `?` koyduğunuz
bir metni kopyaladığınızda, yerel Ollama modeline gönderilir ve cevap otomatik
olarak panonuza yazılır — `Cmd+V` / `Ctrl+V` ile yapıştırırsınız.

## Platformlar

| Platform | Klasör / Dosya | Kurulum |
|----------|----------------|---------|
| **macOS** | [`macos/`](macos/) | `cd macos && ./install.sh` — Ollama'yı ve bağımlılıkları otomatik kurar, LaunchAgent ile hemen başlatır |
| **Windows** | [`monitor.py`](monitor.py) | `install.bat` ile bağımlılıklar, `build_exe.bat` ile tek `.exe` |

## Özellikler

- **`?` ile tetikleme:** `?bu metni özetle …` kopyalayın → cevap panoda.
- **Hızlı soru kısayolu:** macOS `Cmd+Alt+Space`, Windows `Ctrl+Alt+Space`.
- **Görünmeden yazma:** `auto_type` açıkken cevap panoya değil doğrudan
  odaklı alana yazılır.
- **Menü çubuğu / tepsi simgesi:** 🟢 bekliyor · 🟡 işleniyor · 🔴 hata.
- **Otomatik başlatma:** macOS LaunchAgent, Windows kayıt defteri.

macOS kurulum ayrıntıları için [`macos/README.md`](macos/README.md) dosyasına
bakın.
