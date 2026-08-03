#!/usr/bin/env python3
"""
Clipboard AI — macOS sürümü (Ollama ile pano izleme)

'?' ile başlayan kopyalanan metni Ollama'ya gönderir, cevabı panoya yazar.
Menü çubuğu (menubar) simgesi ile durum gösterir; hızlı soru için kısayol ve
isteğe bağlı "görünmeden yazma" (otomatik daktilo) özelliği vardır.

Bağımlılıklar: requests, pyperclip, pynput, rumps  (pyobjc rumps ile gelir)
Bildirim ve panoya erişim için macOS'un yerleşik pbcopy/pbpaste + osascript
kullanılır, ek bağımlılık gerektirmez.
"""
import os
import sys
import json
import time
import hashlib
import logging
import threading
import subprocess

import requests
import pyperclip
import rumps

try:
    from pynput import keyboard as pynput_keyboard
    _HAS_PYNPUT = True
except Exception:  # pynput yoksa kısayol/otomatik yazma devre dışı kalır
    _HAS_PYNPUT = False

# ---------------------------------------------------------------------------
# Yollar & Yapılandırma
# ---------------------------------------------------------------------------
APP_DIR = os.path.join(
    os.path.expanduser("~"),
    "Library", "Application Support", "ollama-clipboard",
)
os.makedirs(APP_DIR, exist_ok=True)

LOG_PATH = os.path.join(APP_DIR, "monitor.log")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "ollama_url": "http://localhost:11434/api/generate",
    "model": "qwen2.5:7b",
    "system_prompt": (
        "Kullanıcının isteğini birebir yap. Ekstra açıklama, yorum veya format "
        "ekleme. Sadece sonucu ver. Türkçe sorulursa Türkçe cevap ver."
    ),
    "poll_interval": 1.5,
    "timeout": 120,
    # Cmd+Alt+Space — hızlı soru penceresini açar (pynput biçimi)
    "quick_input_hotkey": "<cmd>+<alt>+<space>",
    # True ise cevap panoya yazılmaz, doğrudan odaklı alana "görünmeden" yazılır
    "auto_type": False,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    return DEFAULT_CONFIG.copy()


cfg = load_config()

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ---------------------------------------------------------------------------
# Paylaşılan durum (thread-safe)
# ---------------------------------------------------------------------------
STATUS_ICON = {"bekliyor": "🟢", "isleniyor": "🟡", "hata": "🔴"}
STATUS_LABEL = {"bekliyor": "Bekliyor", "isleniyor": "İşleniyor…", "hata": "Hata!"}


class AppState:
    def __init__(self):
        self.status = "bekliyor"
        self.last_query = ""
        self.last_response = ""
        self._lock = threading.Lock()

    def update(self, **kw):
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def snapshot(self):
        with self._lock:
            return self.status, self.last_query, self.last_response


state = AppState()

# ---------------------------------------------------------------------------
# Pano & Bildirim yardımcıları
# ---------------------------------------------------------------------------
def get_clipboard() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def set_clipboard(text: str):
    try:
        pyperclip.copy(text)
    except Exception as e:
        logging.error("Pano yazma hatası: %s", e)


def notify(message: str, title: str = "Clipboard AI"):
    """macOS yerleşik bildirimi — osascript ile, ek bağımlılık yok."""
    try:
        safe_msg = message.replace('"', "'")[:200]
        safe_title = title.replace('"', "'")
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_msg}" with title "{safe_title}"'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logging.warning("Bildirim gönderilemedi: %s", e)


def type_text(text: str):
    """Odaklı alana metni doğrudan yazar (görünmeden yazma)."""
    if not _HAS_PYNPUT:
        logging.warning("pynput yok — otomatik yazma atlandı")
        return
    try:
        controller = pynput_keyboard.Controller()
        time.sleep(0.15)
        controller.type(text)
    except Exception as e:
        logging.error("Otomatik yazma hatası: %s", e)


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
def query_ollama(prompt: str, cancel_event: threading.Event):
    try:
        payload = {"model": cfg["model"], "prompt": prompt, "stream": False}
        if cfg.get("system_prompt"):
            payload["system"] = cfg["system_prompt"]
        resp = requests.post(cfg["ollama_url"], json=payload,
                             timeout=(5, cfg["timeout"]))
        if cancel_event.is_set():
            return None
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        notify("Ollama zaman aşımı", "Clipboard AI Hata")
        return None
    except requests.exceptions.ConnectionError:
        notify("Ollama'ya bağlanılamıyor (ollama serve çalışıyor mu?)",
               "Clipboard AI Hata")
        return None
    except Exception as e:
        notify(f"Hata: {str(e)[:60]}", "Clipboard AI Hata")
        return None


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_processable(text: str) -> bool:
    s = text.strip()
    return s.startswith("?") and len(s) > 1


# ---------------------------------------------------------------------------
# Pano izleyici
# ---------------------------------------------------------------------------
class ClipboardMonitor:
    def __init__(self):
        self.last_hash = content_hash(get_clipboard())
        self.last_ai_response = None
        self.current_cancel = threading.Event()
        self._lock = threading.Lock()
        self.running = True

    def handle(self, prompt: str):
        with self._lock:
            self.current_cancel.set()
            cancel = threading.Event()
            self.current_cancel = cancel

        state.update(status="isleniyor", last_query=prompt)
        logging.info("Yeni soru: %r", prompt[:80])
        notify("Ollama'ya gönderiliyor…")

        response = query_ollama(prompt, cancel)

        if cancel.is_set():
            return
        if response is None:
            state.update(status="hata")
            return

        logging.info("Cevap: %r", response[:80])
        state.update(status="bekliyor", last_response=response)
        self.last_ai_response = response

        if cfg.get("auto_type"):
            # Görünmeden yazma: cevabı doğrudan odaklı alana daktilo et
            notify("Cevap yazılıyor…")
            type_text(response)
        else:
            self.last_hash = content_hash(response)
            set_clipboard(response)
            notify("Cevap hazır — yapıştırabilirsiniz!")

    def run(self):
        logging.info("Monitor başladı. Model: %s", cfg["model"])
        notify("Clipboard AI başladı — '?' ile başlayan metni kopyalayın")
        while self.running:
            time.sleep(cfg["poll_interval"])
            try:
                current = get_clipboard()
                h = content_hash(current)
                if h == self.last_hash:
                    continue
                self.last_hash = h
                if self.last_ai_response is not None and current == self.last_ai_response:
                    continue
                if not is_processable(current):
                    continue
                clean = current.strip()[1:].strip()
                threading.Thread(target=self.handle, args=(clean,),
                                 daemon=True).start()
            except Exception as e:
                logging.error("Poll hatası: %s", e)

    def stop(self):
        self.running = False
        self.current_cancel.set()


# ---------------------------------------------------------------------------
# Menü çubuğu uygulaması (rumps — ana thread)
# ---------------------------------------------------------------------------
class ClipboardAIApp(rumps.App):
    def __init__(self):
        super().__init__("🟢", quit_button=None)
        self.monitor = ClipboardMonitor()
        self._ask_requested = threading.Event()

        self.item_status = rumps.MenuItem("Bekliyor")
        self.item_model = rumps.MenuItem(f"Model: {cfg['model']}")
        self.item_query = rumps.MenuItem("Son Soru: —")
        self.item_response = rumps.MenuItem("Son Cevap: —")
        self.menu = [
            self.item_status,
            self.item_model,
            None,
            self.item_query,
            self.item_response,
            None,
            rumps.MenuItem("Hızlı Soru…", callback=self.on_ask),
            rumps.MenuItem("Logu Aç", callback=self.on_open_log),
            None,
            rumps.MenuItem("Çıkış", callback=self.on_quit),
        ]

        threading.Thread(target=self.monitor.run, daemon=True).start()
        self._start_hotkey()
        # Menubar ana thread'de; durumu periyodik tazele + kısayol isteğini işle
        self._timer = rumps.Timer(self._tick, 0.8)
        self._timer.start()

    def _start_hotkey(self):
        if not _HAS_PYNPUT:
            logging.warning("pynput yok — hızlı soru kısayolu devre dışı")
            return
        try:
            hk = pynput_keyboard.GlobalHotKeys(
                {cfg["quick_input_hotkey"]: self._ask_requested.set}
            )
            hk.daemon = True
            hk.start()
            logging.info("Hızlı soru kısayolu: %s", cfg["quick_input_hotkey"])
        except Exception as e:
            logging.warning("Kısayol atanamadı: %s", e)

    def _tick(self, _timer):
        # Kısayol isteğini ana thread'de karşıla (rumps UI ana thread ister)
        if self._ask_requested.is_set():
            self._ask_requested.clear()
            self.on_ask(None)

        status, query, response = state.snapshot()
        self.title = STATUS_ICON.get(status, "🟢")
        self.item_status.title = STATUS_LABEL.get(status, status)
        if query:
            self.item_query.title = f"Son Soru: {query[:48]}"
        if response:
            self.item_response.title = f"Son Cevap: {response[:48]}"

    def on_ask(self, _sender):
        win = rumps.Window(
            title="Clipboard AI — Hızlı Soru",
            message="Sorunuzu yazın (başına '?' koymanıza gerek yok):",
            default_text="",
            ok="Gönder",
            cancel="İptal",
            dimensions=(360, 100),
        )
        resp = win.run()
        if resp.clicked and resp.text.strip():
            threading.Thread(target=self.monitor.handle,
                             args=(resp.text.strip(),), daemon=True).start()

    def on_open_log(self, _sender):
        subprocess.Popen(["open", LOG_PATH])

    def on_quit(self, _sender):
        self.monitor.stop()
        rumps.quit_application()


if __name__ == "__main__":
    ClipboardAIApp().run()
