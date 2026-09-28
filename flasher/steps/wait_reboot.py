"""
wait_reboot.py - Deteksi modem reboot via ping + port check.
Pengganti "restart modem 1-2 menit boot up" di step.md:15-17.
Tanpa dependensi eksternal, pakai subprocess ping + socket.
"""
import subprocess
import socket
import time
import platform
import shutil


def _log(msg, level="INFO"):
    prefix = {"INFO": "[*]", "OK": "[OK]", "WARN": "[!]", "ERR": "[ERR]"}
    print(f"{prefix.get(level, '[*]')} {msg}")


def ping_once(host, timeout=1):
    """Return True jika ping berhasil (1 paket). Cross-platform."""
    system = platform.system().lower()
    # cari binary ping
    ping_bin = shutil.which("ping")
    if not ping_bin:
        # fallback: coba socket connect ke 80 sebagai "ping" kasar
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, 80))
            s.close()
            return True
        except Exception:
            return False

    if system == "windows":
        # Windows: ping -n 1 -w timeout_ms
        cmd = [ping_bin, "-n", "1", "-w", str(int(timeout * 1000)), host]
    else:
        # Linux/Android/macOS: ping -c 1 -W timeout
        # di Termux ping ada tapi opsi -W kadang beda, coba -w juga
        # Linux: -W timeout sec, macOS: -t timeout
        if system == "darwin":
            cmd = [ping_bin, "-c", "1", "-t", str(int(timeout)), host]
        else:
            cmd = [ping_bin, "-c", "1", "-W", str(int(timeout)), host]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout+2)
        return result.returncode == 0
    except Exception:
        return False


def port_open(host, port, timeout=2):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def wait_for_down(host, timeout=60, poll=1, verbose=True):
    """Tunggu sampai host TIDAK merespon ping (modem mulai reboot). Return True jika sempat down."""
    if verbose:
        _log(f"Menunggu {host} mati (reboot mulai)... timeout {timeout}s")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not ping_once(host, timeout=1):
            if verbose:
                _log(f"{host} tidak merespon - reboot terdeteksi", "OK")
            return True
        time.sleep(poll)
    if verbose:
        _log(f"{host} masih hidup setelah {timeout}s - mungkin sudah lewat fase down atau tidak reboot", "WARN")
    return False


def wait_for_up(host, timeout=120, poll=2, verbose=True):
    """Tunggu sampai host merespon ping lagi (boot selesai)."""
    if verbose:
        _log(f"Menunggu {host} hidup kembali... timeout {timeout}s")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ping_once(host, timeout=1):
            if verbose:
                _log(f"{host} sudah ping balik", "OK")
            return True
        time.sleep(poll)
    if verbose:
        _log(f"{host} tidak kunjung hidup setelah {timeout}s", "ERR")
    return False


def wait_for_port(host, port=23, timeout=90, poll=2, verbose=True):
    """Tunggu sampai port (telnet 23 atau http 80) terbuka."""
    if verbose:
        _log(f"Menunggu port {host}:{port} terbuka... timeout {timeout}s")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(host, port, timeout=2):
            if verbose:
                _log(f"Port {host}:{port} sudah terbuka", "OK")
            return True
        time.sleep(poll)
    if verbose:
        _log(f"Port {host}:{port} tidak terbuka setelah {timeout}s", "WARN")
    return False


def wait_reboot(host, down_timeout=60, up_timeout=120, port_timeout=60, verbose=True):
    """
    Urutan lengkap tunggu reboot:
      1. tunggu down (opsional, kalau tidak down dalam timeout tetap lanjut)
      2. tunggu ping up
      3. tunggu port 23 (telnet) dan 80 (web) siap
    Return True jika minimal ping up.
    """
    if verbose:
        _log(f"=== Tunggu reboot {host} ===")
    wait_for_down(host, timeout=down_timeout, verbose=verbose)
    # beri jeda
    time.sleep(3)
    if not wait_for_up(host, timeout=up_timeout, verbose=verbose):
        return False
    # tunggu telnet + web
    wait_for_port(host, port=23, timeout=port_timeout, verbose=verbose)
    wait_for_port(host, port=80, timeout=20, verbose=verbose)
    if verbose:
        _log(f"Reboot {host} selesai, siap lanjut step berikutnya", "OK")
    return True


def wait_reboot_simple(host, total_timeout=150, verbose=True):
    """Versi sederhana: tunggu ping up + telnet open tanpa fase down."""
    if verbose:
        _log(f"Menunggu {host} siap (ping + telnet)... {total_timeout}s")
    return wait_for_up(host, timeout=total_timeout, verbose=verbose) and wait_for_port(host, 23, timeout=30, verbose=verbose)
