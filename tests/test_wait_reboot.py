"""Test penunggu reboot (steps/wait_reboot.py) dengan ping/port palsu."""
import steps.wait_reboot as wr
from helpers import FakeClock


def no_sleep(monkeypatch, step=1.0):
    monkeypatch.setattr(wr, "time", FakeClock(step))


class FakeConnSock:
    """Socket minimal untuk fallback `ping_once` (connect ke port 80)."""

    def __init__(self, ok=True):
        self.ok = ok

    def settimeout(self, t):
        pass

    def connect(self, addr):
        if not self.ok:
            raise OSError("connection refused")

    def close(self):
        pass


# --- ping_once ------------------------------------------------------------

def test_ping_via_binary_sukses(monkeypatch):
    monkeypatch.setattr(wr.shutil, "which", lambda name: "/usr/bin/ping")
    monkeypatch.setattr(wr.platform, "system", lambda: "Linux")

    class R:
        returncode = 0

    monkeypatch.setattr(wr.subprocess, "run", lambda *a, **k: R())
    assert wr.ping_once("192.168.100.1") is True


def test_ping_via_binary_gagal(monkeypatch):
    monkeypatch.setattr(wr.shutil, "which", lambda name: "/usr/bin/ping")
    monkeypatch.setattr(wr.platform, "system", lambda: "Linux")

    class R:
        returncode = 1

    monkeypatch.setattr(wr.subprocess, "run", lambda *a, **k: R())
    assert wr.ping_once("192.168.100.1") is False


def test_ping_fallback_socket_berhasil(monkeypatch):
    """Kalau `ping` tidak ada (mis. Termux minimal), pakai connect ke port 80."""
    monkeypatch.setattr(wr.shutil, "which", lambda name: None)
    monkeypatch.setattr(wr.socket, "socket", lambda *a, **k: FakeConnSock(True))
    assert wr.ping_once("192.168.100.1", timeout=1) is True


def test_ping_fallback_socket_gagal(monkeypatch):
    monkeypatch.setattr(wr.shutil, "which", lambda name: None)
    monkeypatch.setattr(wr.socket, "socket", lambda *a, **k: FakeConnSock(False))
    assert wr.ping_once("192.168.100.1", timeout=1) is False


# --- wait_for_down / up / port -------------------------------------------

def test_wait_for_down_terdeteksi(monkeypatch):
    monkeypatch.setattr(wr, "ping_once", lambda host, timeout=1: False)
    no_sleep(monkeypatch)
    assert wr.wait_for_down("h", timeout=5, poll=1, verbose=False) is True


def test_wait_for_down_tidak_pernah_mati(monkeypatch):
    monkeypatch.setattr(wr, "ping_once", lambda host, timeout=1: True)
    no_sleep(monkeypatch)
    assert wr.wait_for_down("h", timeout=3, poll=1, verbose=False) is False


def test_wait_for_up_berhasil(monkeypatch):
    monkeypatch.setattr(wr, "ping_once", lambda host, timeout=1: True)
    no_sleep(monkeypatch)
    assert wr.wait_for_up("h", timeout=5, poll=1, verbose=False) is True


def test_wait_for_up_timeout(monkeypatch):
    monkeypatch.setattr(wr, "ping_once", lambda host, timeout=1: False)
    no_sleep(monkeypatch)
    assert wr.wait_for_up("h", timeout=3, poll=1, verbose=False) is False


def test_wait_for_port_terbuka(monkeypatch):
    monkeypatch.setattr(wr, "port_open", lambda host, port, timeout=2: True)
    no_sleep(monkeypatch)
    assert wr.wait_for_port("h", 23, timeout=3, verbose=False) is True


def test_wait_for_port_timeout(monkeypatch):
    monkeypatch.setattr(wr, "port_open", lambda host, port, timeout=2: False)
    no_sleep(monkeypatch)
    assert wr.wait_for_port("h", 23, timeout=3, verbose=False) is False


# --- wait_reboot ----------------------------------------------------------

def test_wait_reboot_sukses(monkeypatch):
    monkeypatch.setattr(wr, "ping_once", lambda host, timeout=1: True)
    monkeypatch.setattr(wr, "port_open", lambda host, port, timeout=2: True)
    no_sleep(monkeypatch)
    assert wr.wait_reboot("h", down_timeout=3, up_timeout=3,
                          port_timeout=3, verbose=False) is True


def test_wait_reboot_gagal_kalau_tidak_pernah_ping_balik(monkeypatch):
    monkeypatch.setattr(wr, "ping_once", lambda host, timeout=1: False)
    monkeypatch.setattr(wr, "port_open", lambda host, port, timeout=2: True)
    no_sleep(monkeypatch)
    assert wr.wait_reboot("h", down_timeout=2, up_timeout=2,
                          port_timeout=2, verbose=False) is False
