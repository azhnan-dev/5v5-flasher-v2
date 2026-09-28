"""
ui.py - Lapisan TAMPILAN saja (tidak menyentuh logika/method).

Memberi tampilan terminal yang enak dilihat:
  - banner besar
  - warna ANSI (otomatis mati kalau output bukan terminal / dipipe)
  - indikator STEP + progress bar
  - kotak alert untuk "CABUT / COLOK modem"
  - spinner saat menunggu
  - tabel ringkasan

Aman di Linux, Termux, dan Windows (VT + UTF-8 diaktifkan otomatis).
Kalau console tidak mendukung Unicode, otomatis pakai karakter ASCII.
Kalau output dipipe ke file (bukan TTY), otomatis jadi teks polos.
"""
import os
import re
import sys
import time
import shutil
import threading

# --------------------------------------------------------------------------
# deteksi kemampuan terminal
# --------------------------------------------------------------------------
def _enable_windows_vt():
    """Aktifkan dukungan ANSI escape di console Windows."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        pass
    return False


def _set_windows_utf8():
    """Set codepage console ke UTF-8 supaya karakter kotak tidak rusak."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass


def _stdout_encoding():
    try:
        return (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "")
    except Exception:
        return ""


def _supports_unicode():
    enc = _stdout_encoding()
    if enc in ("utf8", "utf8mb4", "cp65001", "utf"):
        return True
    if enc in ("", "ascii", "cp1252", "cp437", "cp850", "latin1", "iso88591"):
        return False
    return "utf" in enc


UNICODE = _supports_unicode()
PLAIN = False


def setup_console():
    """Panggil sekali di awal. Tidak mengubah data, hanya kemampuan tampilan."""
    global UNICODE, G
    if os.name == "nt":
        _set_windows_utf8()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    UNICODE = _supports_unicode() and not PLAIN
    G = _U if UNICODE else _A


def _forced():
    return os.environ.get("FLASHER_UI", "") not in ("", "0", "false", "no")


def _is_tty():
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


USE_COLOR = (_is_tty() or _forced()) and os.environ.get("NO_COLOR") is None
if USE_COLOR:
    USE_COLOR = _enable_windows_vt() or _forced()


def set_plain(value=True):
    """Matikan warna + banner (output polos / untuk scripting)."""
    global PLAIN, USE_COLOR, RESET, BOLD, DIM, C, G, UNICODE
    PLAIN = bool(value)
    if PLAIN:
        USE_COLOR = False
        UNICODE = False
        RESET = BOLD = DIM = ""
        C = {}
        G = _A


def term_width(default=80):
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


# --------------------------------------------------------------------------
# warna
# --------------------------------------------------------------------------
RESET = "\033[0m" if USE_COLOR else ""
BOLD = "\033[1m" if USE_COLOR else ""
DIM = "\033[2m" if USE_COLOR else ""
C = {
    "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
    "red": "\033[31m", "magenta": "\033[35m", "blue": "\033[34m",
    "white": "\033[97m", "grey": "\033[90m",
} if USE_COLOR else {}

_ANSI = re.compile(r"\033\[[0-9;]*m")


def vis_len(s):
    return len(_ANSI.sub("", s))


def paint(text, color=None, bold=False, dim=False):
    if not USE_COLOR:
        return text
    p = ""
    if bold:
        p += BOLD
    if dim:
        p += DIM
    if color and color in C:
        p += C[color]
    return f"{p}{text}{RESET}" if p else text


def pad(s, width):
    return s + " " * max(0, width - vis_len(s))


# --------------------------------------------------------------------------
# glyph: Unicode kalau didukung, kalau tidak otomatis ASCII
# --------------------------------------------------------------------------
_U = {
    "tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║",
    "ml": "╟", "mr": "╢", "h2": "─",
    "full": "█", "empty": "░", "dot": "·", "raquo": "»",
    "check": "✔", "cross": "✖", "bullet": "•", "tri": "▶", "ell": "…",
}
_A = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "=", "v": "|",
    "ml": "+", "mr": "+", "h2": "-",
    "full": "#", "empty": ".", "dot": "-", "raquo": ">",
    "check": "v", "cross": "x", "bullet": "*", "tri": ">", "ell": "...",
}
G = _U if UNICODE else _A


def _g(key):
    return (G if not PLAIN else _A).get(key, "")


def sym(key):
    """Ambil simbol (Unicode kalau didukung, ASCII kalau tidak)."""
    return _g(key)


# --------------------------------------------------------------------------
# komponen
# --------------------------------------------------------------------------
BIG_TITLE = [
    " ███████╗ ██╗   ██╗ ███████╗   ███████╗██╗      █████╗ ███████╗██╗  ██╗███████╗██████╗ ",
    " ██╔════╝ ██║   ██║ ██╔════╝   ██╔════╝██║     ██╔══██╗██╔════╝██║  ██║██╔════╝██╔══██╗",
    " ███████╗ ██║   ██║ ███████╗   █████╗  ██║     ███████║███████╗███████║█████╗  ██████╔╝",
    " ╚════██║ ╚██╗ ██╔╝ ╚════██║   ██╔══╝  ██║     ██╔══██║╚════██║██╔══██║██╔══╝  ██╔══██╗",
    " ███████║  ╚████╔╝  ███████║   ██║     ███████╗██║  ██║███████║██║  ██║███████╗██║  ██║",
    " ╚══════╝   ╚═══╝   ╚══════╝   ╚═╝     ╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝",
]


def banner(subtitle="PORT LINUX / TERMUX  ·  TANPA WINDOWS"):
    """Cetak banner pembuka."""
    if PLAIN:
        print()
        print(f"5v5 FLASHER - {subtitle}")
        print()
        return
    w = term_width()
    print()
    if UNICODE and w >= 92:
        for line in BIG_TITLE:
            print(paint(line, "cyan", bold=True))
        print(paint(f"   {subtitle}", "grey"))
    else:
        title = "5v5 FLASHER"
        inner = max(20, w - 4)
        h, v = _g("h"), _g("v")
        print(paint(_g("tl") + h * (inner + 2) + _g("tr"), "cyan", bold=True))
        print(paint(v + " ", "cyan") + paint(pad(title, inner), "white", bold=True) + paint(f" {v}", "cyan"))
        print(paint(v + " ", "cyan") + paint(pad(subtitle, inner), "grey") + paint(f" {v}", "cyan"))
        print(paint(_g("bl") + h * (inner + 2) + _g("br"), "cyan", bold=True))
    print()


def rule(label="", color="cyan"):
    w = term_width()
    h = _g("h2")
    if label:
        lbl = f" {label} "
        n = max(0, w - vis_len(lbl) - 2)
        left = n // 2
        print(paint(h * left + lbl + h * (n - left), color))
    else:
        print(paint(h * w, color))


def kv(key, value, color="white", keyw=12):
    print(f"  {paint(pad(key, keyw), 'grey')}: {paint(str(value), color)}")


STEP_TOTAL = 8
_STEP_NAMES = ["LOGIN", "IDENTITAS", "BACKUP CONFIG", "UPLOAD CONFIG DEFAULT",
               "FLASH FIRMWARE", "EQUIPMODE", "SET EPON", "VERIFIKASI"]


def progress(n, total=STEP_TOTAL, width=None):
    if width is None:
        width = max(10, min(40, term_width() - 30))
    filled = int(width * n / total) if total else 0
    bar = _g("full") * filled + _g("empty") * (width - filled)
    pct = int(100 * n / total) if total else 0
    col = "green" if n >= total else ("yellow" if n > total / 2 else "cyan")
    return f"{paint('[' + bar + ']', col)} {n}/{total} {pct:3d}%"


def step(n, title=None, total=STEP_TOTAL):
    """Tandai awal sebuah STEP dengan progress bar."""
    title = title or (_STEP_NAMES[n - 1] if 1 <= n <= len(_STEP_NAMES) else "")
    if PLAIN:
        print(f"\n[STEP {n}/{total}] {title}")
        return
    print()
    print(f"{paint(_g('tri'), 'magenta', bold=True)} {paint(f'STEP {n}/{total}', 'magenta', bold=True)}"
          f"  {paint(title, 'white', bold=True)}")
    print(f"  {progress(n, total)}")


def log(msg, level="INFO"):
    """Log standar (warna + ikon + timestamp)."""
    ts = time.strftime("%H:%M:%S")
    icons = {"INFO": ("bullet", "cyan"), "OK": ("check", "green"), "WARN": ("cross", "yellow"),
             "ERR": ("cross", "red"), "STEP": ("raquo", "magenta")}
    key, col = icons.get(level, ("bullet", "cyan"))
    if PLAIN:
        tag = {"INFO": "*", "OK": "OK", "WARN": "!", "ERR": "ERR", "STEP": ">"}.get(level, "*")
        print(f"[{ts}] {tag} {msg}", flush=True)
        return
    print(f"  {paint(_g(key), col, bold=True)} {paint(f'[{ts}]', 'grey')} "
          f"{paint(msg, col if level != 'INFO' else None)}", flush=True)


def alert(lines, title="", color="yellow", icon=""):
    """Kotak alert besar."""
    if isinstance(lines, str):
        lines = [lines]
    if PLAIN:
        print()
        print(f"=== {title} ===")
        for ln in lines:
            print(ln)
        print()
        return
    w = min(term_width() - 2, 74)
    inner = max(24, w - 4)
    h, v = _g("h"), _g("v")
    print()
    print(paint(_g("tl") + h * (inner + 2) + _g("tr"), color, bold=True))
    if title:
        head = f"{icon}  {title}".strip()
        print(paint(v + " ", color, bold=True) + paint(pad(head, inner), "white", bold=True)
              + paint(f" {v}", color, bold=True))
        print(paint(_g("ml") + _g("h2") * (inner + 2) + _g("mr"), color))
    for ln in lines:
        ln = str(ln)
        if vis_len(ln) > inner:
            ln = ln[:inner - len(_g("ell"))] + _g("ell")
        print(paint(v + " ", color) + pad(ln, inner) + paint(f" {v}", color))
    print(paint(_g("bl") + h * (inner + 2) + _g("br"), color, bold=True))
    print()


def success_big(serial, model="", extra=""):
    alert([f"MODEM SELESAI  {_g('dot')}  SN {serial}",
           f"{model} {(_g('dot') + ' ' + extra) if extra else ''}".strip(),
           "",
           f"{_g('raquo')}{_g('raquo')}{_g('raquo')}  CABUT modem ini, lalu COLOK modem berikutnya  "
           f"{_g('raquo')}{_g('raquo')}{_g('raquo')}"],
          title="BERHASIL", color="green", icon=_g("check"))
    _beep()


def fail_big(serial, note=""):
    alert([f"MODEM GAGAL  {_g('dot')}  SN {serial}", note,
           "", f"{_g('raquo')}{_g('raquo')}{_g('raquo')}  CABUT modem ini untuk lanjut  "
               f"{_g('raquo')}{_g('raquo')}{_g('raquo')}"],
          title="GAGAL", color="red", icon=_g("cross"))
    _beep()


def _beep():
    try:
        sys.stdout.write("\a")
        sys.stdout.flush()
    except Exception:
        pass


def table(rows, headers=None, maxw=46):
    """Tabel sederhana, lebar kolom otomatis (tampilan saja)."""
    if not rows:
        return
    rows = [[str(c) for c in r] for r in rows]
    ncol = max(len(r) for r in rows)
    for r in rows:
        while len(r) < ncol:
            r.append("")

    def clip(s):
        return s if vis_len(s) <= maxw else s[:maxw - 1] + (_g("ell") or ".")

    rows = [[clip(c) for c in r] for r in rows]
    hdrs = [clip(str(h)) for h in headers] if headers else None
    widths = [0] * ncol
    for r in ([hdrs] if hdrs else []) + rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], vis_len(c))
    if hdrs:
        print("   " + "  ".join(paint(pad(hdrs[i], widths[i]), "grey", bold=True) for i in range(ncol)))
        print("   " + paint("  ".join(_g("h2") * widths[i] for i in range(ncol)), "grey"))
    for r in rows:
        cells = []
        for i, c in enumerate(r):
            col = None
            if i == 3:
                col = ("green" if c.startswith("ok") else
                       "yellow" if c.startswith("warn") or c.startswith("dry") else
                       "red" if c.startswith("fail") else None)
            cells.append(paint(pad(c, widths[i]), col))
        print("   " + "  ".join(cells))


# --------------------------------------------------------------------------
# spinner (animasi saat menunggu) - murni tampilan
# --------------------------------------------------------------------------
class Spinner:
    def __init__(self, msg):
        self.msg = msg
        self._stop = threading.Event()
        self._t = None
        self.live = USE_COLOR and _is_tty() and not PLAIN

    def __enter__(self):
        if self.live:
            self._t = threading.Thread(target=self._run, daemon=True)
            self._t.start()
        elif self.msg and not PLAIN:
            print(f"  {paint(_g('bullet'), 'cyan')} {self.msg} ...", flush=True)
        elif self.msg:
            print(f"  - {self.msg} ...", flush=True)
        return self

    def _run(self):
        frames = "-\\|/"
        i = 0
        while not self._stop.is_set():
            sys.stdout.write(f"\r  {paint(frames[i % 4], 'yellow', bold=True)} {self.msg}   ")
            sys.stdout.flush()
            i += 1
            time.sleep(0.12)

    def __exit__(self, *exc):
        self._stop.set()
        if self._t:
            self._t.join(timeout=0.6)
            line = f"  - {self.msg}   "
            sys.stdout.write("\r" + " " * vis_len(line) + "\r")
            sys.stdout.flush()
        return False


def wait_line(msg):
    """Versi sederhana tanpa animasi."""
    print(f"  {paint(_g('bullet'), 'cyan')} {msg}", flush=True)
