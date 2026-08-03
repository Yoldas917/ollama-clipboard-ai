#!/usr/bin/env python3
"""
Windows Clipboard AI — Ollama ile pano izleme
'?' ile başlayan kopyalanan metni Ollama'ya gönderir, cevabı panoya yazar.
"""
import os, sys, json, hashlib, time, threading, logging, queue
import tkinter as tk
import requests
import pyperclip
import pystray
from PIL import Image, ImageDraw
import keyboard
import plyer.utils
from plyer import notification as plyer_notification

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------
APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ollama-clipboard")
os.makedirs(APP_DIR, exist_ok=True)

LOG_PATH    = os.path.join(APP_DIR, "monitor.log")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "ollama_url":         "http://localhost:11434/api/generate",
    "model":              "qwen2.5:7b",
    "system_prompt":      "Kullanıcının isteğini birebir yap. Ekstra açıklama, yorum veya format ekleme. Sadece sonucu ver. Türkçe sorulursa Türkçe cevap ver.",
    "poll_interval":      1.5,
    "timeout":            120,
    "quick_input_hotkey": "ctrl+alt+space",
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

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)

# ---------------------------------------------------------------------------
# Shared state (thread-safe)
# ---------------------------------------------------------------------------
class AppState:
    def __init__(self):
        self.status        = "bekliyor"   # bekliyor | isleniyor | hata
        self.last_query    = ""
        self.last_response = ""
        self._lock         = threading.Lock()

    def update(self, **kw):
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def snapshot(self):
        with self._lock:
            return self.status, self.last_query, self.last_response

state = AppState()

# UI thread-safe queue — tkinter only touched from main thread via this queue
_ui_q: queue.SimpleQueue = queue.SimpleQueue()

# ---------------------------------------------------------------------------
# Clipboard helpers
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

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
def notify(message: str, title: str = "Clipboard AI"):
    try:
        plyer_notification.notify(
            title=title,
            message=message,
            app_name="Clipboard AI",
            timeout=5,
        )
    except Exception as e:
        logging.warning("Bildirim gönderilemedi: %s", e)

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
def query_ollama(prompt: str, cancel_event: threading.Event):
    try:
        payload = {
            "model":  cfg["model"],
            "prompt": prompt,
            "stream": False,
        }
        if cfg.get("system_prompt"):
            payload["system"] = cfg["system_prompt"]
        resp = requests.post(
            cfg["ollama_url"],
            json=payload,
            timeout=(5, cfg["timeout"]),
        )
        if cancel_event.is_set():
            return None
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        notify("Ollama zaman aşımı", "Clipboard AI Hata")
        return None
    except requests.exceptions.ConnectionError:
        notify("Ollama'ya bağlanılamıyor", "Clipboard AI Hata")
        return None
    except Exception as e:
        notify(f"Hata: {str(e)[:60]}", "Clipboard AI Hata")
        return None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def is_processable(text: str) -> bool:
    s = text.strip()
    return s.startswith("?") and len(s) > 1

# ---------------------------------------------------------------------------
# Tray icons (generated at runtime with Pillow)
# ---------------------------------------------------------------------------
def _make_icon(color: str) -> Image.Image:
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color, outline=(255, 255, 255, 160), width=2)
    return img

ICON_IDLE  = _make_icon("#4CAF50")   # yeşil — bekliyor
ICON_BUSY  = _make_icon("#FFC107")   # sarı  — işleniyor
ICON_ERROR = _make_icon("#F44336")   # kırmızı — hata

_STATUS_ICON = {"bekliyor": ICON_IDLE, "isleniyor": ICON_BUSY, "hata": ICON_ERROR}

# ---------------------------------------------------------------------------
# Quick Input Popup — açılır, yaz, Enter'a bas, kapanır
# ---------------------------------------------------------------------------
class QuickInputPopup:
    def __init__(self, root: tk.Tk, on_submit):
        self.root      = root
        self.on_submit = on_submit
        self._win      = None

    def show(self):
        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._entry.focus_force()
            return

        win = tk.Toplevel(self.root)
        self._win = win
        win.title("")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.95)
        win.configure(bg="#1e1e1e")

        w, h = 520, 52
        sw   = win.winfo_screenwidth()
        sh   = win.winfo_screenheight()
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh // 3}")

        frame = tk.Frame(win, bg="#252525", padx=10, pady=10)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="❯", bg="#252525", fg="#4CAF50",
                 font=("Segoe UI", 12, "bold")).pack(side="left", padx=(2, 8))

        self._entry = tk.Entry(
            frame,
            bg="#2a2a2a", fg="#dcdcdc",
            font=("Segoe UI", 11),
            relief="flat", bd=0,
            insertbackground="#dcdcdc",
        )
        self._entry.pack(side="left", fill="x", expand=True)
        self._entry.focus_force()

        self._entry.bind("<Return>",  self._send)
        self._entry.bind("<Escape>",  lambda e: self._close())
        win.bind("<FocusOut>",        lambda e: self._close())

    def _send(self, event=None):
        text = self._entry.get().strip()
        self._close()
        if text:
            self.on_submit(text)

    def _close(self):
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None


# ---------------------------------------------------------------------------
# Status Panel (tkinter) — runs in main thread, updated via _ui_q
# ---------------------------------------------------------------------------
class StatusPanel:
    BG       = "#1e1e1e"
    BG2      = "#2a2a2a"
    BG3      = "#141414"
    FG       = "#dcdcdc"
    FG_DIM   = "#888888"
    FONT     = ("Segoe UI", 10)
    FONT_SML = ("Segoe UI", 8)
    MONO     = ("Consolas", 9)

    def __init__(self, root: tk.Tk):
        self.root    = root
        self.visible = False
        self._build()

    # --- build UI -----------------------------------------------------------
    def _build(self):
        r = self.root
        r.title("Clipboard AI")
        r.configure(bg=self.BG)
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", 0.93)
        r.withdraw()

        W = 440
        sw = r.winfo_screenwidth()
        r.geometry(f"{W}+{sw - W - 20}+20")

        r.bind("<ButtonPress-1>",   self._drag_start)
        r.bind("<B1-Motion>",       self._drag_move)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(r, bg="#252525", padx=12, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="◉  Clipboard AI",
                 bg="#252525", fg=self.FG,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(hdr, text="✕",
                  bg="#252525", fg=self.FG_DIM,
                  activebackground="#3a3a3a", activeforeground=self.FG,
                  relief="flat", font=("Segoe UI", 11),
                  cursor="hand2", command=self.hide).pack(side="right")

        tk.Frame(r, bg="#333", height=1).pack(fill="x")

        # ── Status row ──────────────────────────────────────────────────────
        srow = tk.Frame(r, bg=self.BG, padx=12, pady=6)
        srow.pack(fill="x")
        self.lbl_dot = tk.Label(srow, text="●", bg=self.BG, fg="#4CAF50",
                                font=("Segoe UI", 14))
        self.lbl_dot.pack(side="left")
        self.lbl_status = tk.Label(srow, text="Bekliyor",
                                   bg=self.BG, fg="#4CAF50",
                                   font=("Segoe UI", 10, "bold"))
        self.lbl_status.pack(side="left", padx=(4, 16))
        tk.Label(srow, text=f"Model: {cfg['model']}",
                 bg=self.BG, fg=self.FG_DIM,
                 font=self.FONT_SML).pack(side="left")

        tk.Frame(r, bg="#2d2d2d", height=1).pack(fill="x")

        # ── Son Soru ────────────────────────────────────────────────────────
        self._section_label(r, "Son Soru")
        self.txt_query = self._textbox(r, height=2)

        # ── Son Cevap ───────────────────────────────────────────────────────
        self._section_label(r, "Son Cevap")
        self.txt_response = self._textbox(r, height=6)

        tk.Frame(r, bg="#2d2d2d", height=1).pack(fill="x")

        # ── Log ─────────────────────────────────────────────────────────────
        self._section_label(r, "Son Loglar")
        self.txt_log = self._textbox(r, height=4, bg=self.BG3, fg="#777")

        # ── Footer ──────────────────────────────────────────────────────────
        tk.Label(r, text="Ctrl+Alt+Space — hızlı soru  |  Ctrl+Shift+M — panel  |  Tray: sağ tık → Çıkış",
                 bg=self.BG, fg="#555", font=self.FONT_SML).pack(pady=(0, 8))

        # start polling
        self._poll()

    def _section_label(self, parent, text: str):
        tk.Label(parent, text=text,
                 bg=self.BG, fg=self.FG_DIM,
                 font=self.FONT_SML, anchor="w",
                 padx=12, pady=2).pack(fill="x")

    def _textbox(self, parent, height: int,
                 bg: str = None, fg: str = None) -> tk.Text:
        t = tk.Text(parent,
                    height=height,
                    bg=bg or self.BG2, fg=fg or self.FG,
                    font=self.MONO,
                    relief="flat", bd=0,
                    wrap="word",
                    state="disabled",
                    cursor="arrow",
                    padx=10, pady=6,
                    selectbackground="#3a3a3a")
        t.pack(fill="x", padx=12, pady=(0, 6))
        return t

    # --- drag ---------------------------------------------------------------
    def _drag_start(self, e):
        self._ox, self._oy = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._ox
        y = self.root.winfo_y() + e.y - self._oy
        self.root.geometry(f"+{x}+{y}")

    # --- helpers ------------------------------------------------------------
    @staticmethod
    def _set_text(widget: tk.Text, text: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.config(state="disabled")

    @staticmethod
    def _read_log_tail(n: int = 5) -> str:
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return "".join(lines[-n:]).strip()
        except Exception:
            return ""

    # --- periodic refresh ---------------------------------------------------
    def _poll(self):
        # drain the UI queue
        try:
            while True:
                fn = _ui_q.get_nowait()
                fn()
        except Exception:
            pass

        # refresh content
        status, query, response = state.snapshot()
        color = {"bekliyor": "#4CAF50", "isleniyor": "#FFC107", "hata": "#F44336"}.get(status, self.FG)
        labels = {"bekliyor": "Bekliyor", "isleniyor": "İşleniyor...", "hata": "Hata!"}.get(status, status)
        self.lbl_dot.config(fg=color)
        self.lbl_status.config(text=labels, fg=color)
        self._set_text(self.txt_query,    query[:300]    if query    else "(henüz sorgu yok)")
        self._set_text(self.txt_response, response[:600] if response else "(henüz cevap yok)")
        self._set_text(self.txt_log,      self._read_log_tail())

        self.root.after(1200, self._poll)

    # --- toggle / show / hide -----------------------------------------------
    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    def show(self):
        self.visible = True
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self):
        self.visible = False
        self.root.withdraw()


# ---------------------------------------------------------------------------
# Clipboard Monitor
# ---------------------------------------------------------------------------
class ClipboardMonitor:
    def __init__(self, tray_ref: list):
        self.last_hash        = content_hash(get_clipboard())
        self.last_ai_response = None
        self.current_cancel   = threading.Event()
        self._lock            = threading.Lock()
        self.running          = True
        self._tray            = tray_ref   # list so it can be set after init

    def _update_tray(self, status_key: str):
        icon = _STATUS_ICON.get(status_key, ICON_IDLE)
        tooltips = {"bekliyor": "Clipboard AI — Bekliyor", "isleniyor": "Clipboard AI — İşleniyor...", "hata": "Clipboard AI — Hata!"}
        t = self._tray[0]
        if t:
            t.icon  = icon
            t.title = tooltips.get(status_key, "Clipboard AI")

    def _handle(self, prompt: str):
        with self._lock:
            self.current_cancel.set()
            cancel = threading.Event()
            self.current_cancel = cancel

        state.update(status="isleniyor", last_query=prompt)
        self._update_tray("isleniyor")
        logging.info("Yeni soru: %r…", prompt[:80])
        notify("Ollama'ya gönderiliyor…")

        response = query_ollama(prompt, cancel)

        if cancel.is_set():
            return
        if response is None:
            state.update(status="hata")
            self._update_tray("hata")
            return

        logging.info("Cevap: %r…", response[:80])
        state.update(status="bekliyor", last_response=response)
        self._update_tray("bekliyor")
        self.last_ai_response = response
        self.last_hash        = content_hash(response)
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
                threading.Thread(target=self._handle, args=(clean,), daemon=True).start()
            except Exception as e:
                logging.error("Poll hatası: %s", e)

    def stop(self):
        self.running = False
        self.current_cancel.set()
        logging.info("Monitor durduruldu")


# ---------------------------------------------------------------------------
# Windows autostart (registry)
# ---------------------------------------------------------------------------
def setup_autostart():
    if sys.platform != "win32":
        return
    try:
        import winreg
        value = (
            f'"{sys.executable}"'
            if sys.executable.lower().endswith("monitor.exe")
            else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
        )
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "OllamaClipboardAI", 0, winreg.REG_SZ, value)
        winreg.CloseKey(key)
        logging.info("Autostart kaydedildi: %s", value)
    except Exception as e:
        logging.warning("Autostart kaydedilemedi: %s", e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    # ── tkinter (main thread) ───────────────────────────────────────────────
    root = tk.Tk()
    panel = StatusPanel(root)

    # ── Tray ────────────────────────────────────────────────────────────────
    tray_ref: list = [None]
    monitor = ClipboardMonitor(tray_ref)

    # ── Quick Input Popup ───────────────────────────────────────────────────
    def _direct_submit(text: str):
        threading.Thread(target=monitor._handle, args=(text,), daemon=True).start()

    popup = QuickInputPopup(root, on_submit=_direct_submit)

    def on_panel_toggle(icon, item):
        _ui_q.put(panel.toggle)

    def on_open_log(icon, item):
        if sys.platform == "win32":
            os.startfile(LOG_PATH)
        else:
            import subprocess
            subprocess.Popen(["open", LOG_PATH])

    def on_exit(icon, item):
        monitor.stop()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        icon.stop()
        _ui_q.put(root.destroy)

    menu = pystray.Menu(
        pystray.MenuItem("Paneli Göster / Gizle  (Ctrl+Shift+M)", on_panel_toggle, default=True),
        pystray.MenuItem("Log Dosyasını Aç",                       on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Çıkış",                                   on_exit),
    )

    tray = pystray.Icon("clipboard_ai", ICON_IDLE, "Clipboard AI — Bekliyor", menu)
    tray_ref[0] = tray

    # ── Global hotkeys ──────────────────────────────────────────────────────
    try:
        keyboard.add_hotkey("ctrl+shift+m",
                            lambda: _ui_q.put(panel.toggle),
                            suppress=False)
    except Exception as e:
        logging.warning("Panel kısayolu atanamadı: %s", e)

    try:
        keyboard.add_hotkey(cfg["quick_input_hotkey"],
                            lambda: _ui_q.put(popup.show),
                            suppress=False)
        logging.info("Hızlı giriş kısayolu: %s", cfg["quick_input_hotkey"])
    except Exception as e:
        logging.warning("Hızlı giriş kısayolu atanamadı: %s", e)

    # ── Background threads ──────────────────────────────────────────────────
    threading.Thread(target=monitor.run,  daemon=True).start()
    threading.Thread(target=tray.run,     daemon=True).start()

    # ── Autostart ───────────────────────────────────────────────────────────
    setup_autostart()

    # ── tkinter main loop ───────────────────────────────────────────────────
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if tray_ref[0]:
            tray_ref[0].stop()


if __name__ == "__main__":
    main()
