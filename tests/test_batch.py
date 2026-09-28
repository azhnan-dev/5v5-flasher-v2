"""
Test mode stasiun otomatis (steps/batch.py) - dengan HTTP/telnet palsu.

Tidak ada modem, tidak ada jaringan: semua fungsi I/O di-monkeypatch.
"""
import pytest

import steps.batch as batch
from helpers import FakeClock, NoSleepTime

DEVINFO = {
    "SerialNumber": "485754439A1892AF",
    "ModelName": "EG8145V5",
    "SoftwareVersion": "V5R022C10S167",
    "Mac": "08:02:05:E9:79:34",
}


# --- wait_for_removal -----------------------------------------------------

def test_wait_for_removal_selesai_setelah_stabil(monkeypatch):
    monkeypatch.setattr(batch, "detect_modem", lambda hosts, verbose=True: [])
    monkeypatch.setattr(batch, "time", FakeClock(step=3))
    assert batch.wait_for_removal(hosts=["h"], stable=8, poll=2, quiet=True) is True


def test_wait_for_removal_menunggu_modem_baru_hilang(monkeypatch):
    state = {"n": 0}

    def fake_detect(hosts, verbose=True):
        state["n"] += 1
        return ["h"] if state["n"] <= 2 else []

    monkeypatch.setattr(batch, "detect_modem", fake_detect)
    monkeypatch.setattr(batch, "time", FakeClock(step=1))
    assert batch.wait_for_removal(hosts=["h"], stable=2, poll=1, quiet=True) is True
    assert state["n"] >= 4


# --- login_wait -----------------------------------------------------------

def test_login_wait_berhasil_setelah_beberapa_retry(monkeypatch):
    seq = iter([(False, ""), (False, ""), (True, "cookie=abc")])
    monkeypatch.setattr(batch, "login_host", lambda host, verbose=True: next(seq))
    monkeypatch.setattr(batch, "time", FakeClock())
    ok, cookie = batch.login_wait("h", timeout=100, poll=1, quiet=True)
    assert ok is True
    assert cookie == "cookie=abc"


def test_login_wait_menyerah_setelah_timeout(monkeypatch):
    monkeypatch.setattr(batch, "login_host", lambda host, verbose=True: (False, ""))
    monkeypatch.setattr(batch, "time", FakeClock(step=50))
    ok, cookie = batch.login_wait("h", timeout=100, poll=1, quiet=True)
    assert ok is False
    assert cookie == ""


# --- log CSV --------------------------------------------------------------

def test_csv_append_menulis_header_sekali(tmp_path):
    root = str(tmp_path / "backup")
    batch._csv_append(root, {"host": "h1", "status": "ok"})
    batch._csv_append(root, {"host": "h1", "status": "ok"})
    lines = (tmp_path / "backup" / "batch_log.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "host,status"
    assert len(lines) == 3


def test_csv_append_tanpa_backup_root_tidak_error():
    batch._csv_append(None, {"host": "h1"})


# --- process_one ----------------------------------------------------------

def test_process_one_dry_run_hanya_login_dan_backup(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "login_wait",
                        lambda host, timeout=180, quiet=False: (True, "cookie"))
    monkeypatch.setattr(batch, "get_device_info", lambda host, cookie: dict(DEVINFO))

    def fake_download(host, cookie, out, verbose=True):
        with open(out, "wb") as f:
            f.write(b"config-biner")
        return True, "ok 12 byte"

    monkeypatch.setattr(batch, "download_config", fake_download)

    res = batch.process_one("192.168.100.1", None, None,
                            backup_root=str(tmp_path), dry_run=True, quiet=True)
    assert res["status"] == "dry-run"
    assert res["serial_short"] == "HWTC9A1892AF"
    assert res["model"] == "EG8145V5"
    assert res["software"] == "V5R022C10S167"
    d = tmp_path / "HWTC9A1892AF"
    assert d.is_dir()
    assert len(list(d.glob("hw_ctree_awal_*.bin"))) == 1


def test_process_one_login_gagal(monkeypatch):
    monkeypatch.setattr(batch, "login_wait",
                        lambda host, timeout=180, quiet=False: (False, ""))
    res = batch.process_one("192.168.100.1", None, None, dry_run=True, quiet=True)
    assert res["status"] == "failed"
    assert "login" in res["note"]


def test_process_one_upload_config_ditolak(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "login_wait",
                        lambda host, timeout=180, quiet=False: (True, "cookie"))
    monkeypatch.setattr(batch, "get_device_info", lambda host, cookie: dict(DEVINFO))
    monkeypatch.setattr(batch, "download_config", lambda *a, **k: (True, "n/a"))
    monkeypatch.setattr(batch, "upload_xml_auto", lambda *a, **k: False)
    monkeypatch.setattr(batch, "time", NoSleepTime())

    res = batch.process_one("192.168.100.1", "1_1010.xml", None,
                            backup_root=str(tmp_path), quiet=True)
    assert res["status"] == "failed"
    assert res["note"] == "upload config gagal"


def test_process_one_firmware_ditolak(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "login_wait",
                        lambda host, timeout=180, quiet=False: (True, "cookie"))
    monkeypatch.setattr(batch, "get_device_info", lambda host, cookie: dict(DEVINFO))
    monkeypatch.setattr(batch, "download_config", lambda *a, **k: (True, "n/a"))
    monkeypatch.setattr(batch, "upload_xml_auto", lambda *a, **k: True)
    monkeypatch.setattr(batch, "wait_for_modem",
                        lambda hosts=None, poll=3, timeout=None, quiet=False: "192.168.100.1")
    monkeypatch.setattr(batch, "upload_firmware", lambda *a, **k: (False, "ditolak"))
    monkeypatch.setattr(batch, "time", NoSleepTime())

    res = batch.process_one("192.168.100.1", "1_1010.xml", "2 - R022.bin",
                            backup_root=str(tmp_path), quiet=True)
    assert res["status"] == "failed"
    assert res["note"] == "firmware ditolak web"


# --- run_batch (loop station) --------------------------------------------

def _ok_result(serial="485754439A1892AF"):
    return {
        "time": "2026-01-01T00:00:00", "host": "192.168.100.1",
        "serial": serial, "serial_short": "HWTC9A1892AF",
        "model": "EG8145V5", "software": "V5R022C10S167",
        "mac": "08:02:05:E9:79:34", "upport_mode": "2",
        "status": "ok", "note": "EPON aktif (mode=2)",
    }


def test_run_batch_anti_dobel_serial_yang_sama(monkeypatch):
    """Modem dengan Serial Number yang sama TIDAK boleh diproses dua kali."""
    calls = {"process": 0, "removal": 0}

    monkeypatch.setattr(batch, "wait_for_modem", lambda hosts=None, poll=3: "192.168.100.1")
    monkeypatch.setattr(batch, "login_wait",
                        lambda host, timeout=180, quiet=False: (True, "cookie"))
    monkeypatch.setattr(batch, "get_device_info", lambda host, cookie: dict(DEVINFO))
    monkeypatch.setattr(batch, "_csv_append", lambda root, row: None)

    def fake_process(*a, **k):
        calls["process"] += 1
        return _ok_result()

    monkeypatch.setattr(batch, "process_one", fake_process)

    def fake_removal(hosts=None, stable=8, poll=2, quiet=False):
        calls["removal"] += 1
        if calls["removal"] >= 2:
            raise KeyboardInterrupt  # hentikan loop tak terbatas
        return True

    monkeypatch.setattr(batch, "wait_for_removal", fake_removal)

    with pytest.raises(KeyboardInterrupt):
        batch.run_batch(xml=None, bin_path=None, backup_root=None, quiet=True)

    assert calls["process"] == 1, "modem kedua (SN sama) seharusnya dilewati"
    assert calls["removal"] == 2


def test_run_batch_once_menulis_log_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(batch, "wait_for_modem", lambda hosts=None, poll=3: "192.168.100.1")
    monkeypatch.setattr(batch, "login_wait",
                        lambda host, timeout=180, quiet=False: (True, "cookie"))
    monkeypatch.setattr(batch, "get_device_info", lambda host, cookie: dict(DEVINFO))

    dry = _ok_result()
    dry.update({"status": "dry-run", "note": "hanya login+backup (dry-run)"})
    monkeypatch.setattr(batch, "process_one", lambda *a, **k: dict(dry))

    rc = batch.run_batch(xml=None, bin_path=None, backup_root=str(tmp_path),
                         once=True, dry_run=True, quiet=True)
    assert rc == 0
    log = tmp_path / "batch_log.csv"
    assert log.is_file()
    assert "HWTC9A1892AF" in log.read_text(encoding="utf-8")


# --- wait_for_modem / wait_for_telnet (anti-stuck) ------------------------

def test_wait_for_modem_langsung_kembali_kalau_ada(monkeypatch):
    monkeypatch.setattr(batch, "detect_modem", lambda hosts, verbose=True: ["192.168.100.1"])
    monkeypatch.setattr(batch, "time", FakeClock())
    assert batch.wait_for_modem(hosts=["h"], quiet=True) == "192.168.100.1"


def test_wait_for_modem_timeout_tidak_menggantung(monkeypatch):
    """Regresi: dulu `while True` TANPA timeout -> batch stuck selamanya."""
    monkeypatch.setattr(batch, "detect_modem", lambda hosts, verbose=True: [])
    monkeypatch.setattr(batch, "time", FakeClock(step=1))
    assert batch.wait_for_modem(hosts=["h"], poll=1, timeout=5, quiet=True) is None


def test_wait_for_telnet_deteksi_port_23(monkeypatch):
    def fake_port_open(host, port, timeout=2):
        return host == "192.168.100.1" and port == 23

    monkeypatch.setattr(batch, "port_open", fake_port_open)
    monkeypatch.setattr(batch, "time", FakeClock())
    host = batch.wait_for_telnet(hosts=["192.168.18.1", "192.168.100.1"],
                                 timeout=30, quiet=True)
    assert host == "192.168.100.1"


def test_wait_for_telnet_timeout_return_none(monkeypatch):
    monkeypatch.setattr(batch, "port_open", lambda host, port, timeout=2: False)
    monkeypatch.setattr(batch, "time", FakeClock(step=1))
    assert batch.wait_for_telnet(hosts=["h"], timeout=5, poll=1, quiet=True) is None


# --- pemilihan firmware sesuai versi modem --------------------------------

@pytest.mark.parametrize("version,fam", [
    ("V5R020C10S195", "R020"),
    ("V500R022C10SPC167A2309140182", "R022"),
    ("V300R020C10SPC212A2206210275", "R020"),
    ("tidak-ada-versi", ""),
    ("", ""),
    (None, ""),
])
def test_fw_family(version, fam):
    assert batch.fw_family(version) == fam


def test_pick_bin_pilih_sesuai_keluarga():
    m = {"R020": "R020.bin", "R022": "2 - R022.bin"}
    assert batch.pick_bin("V5R020C10S195", "default.bin", m)[0] == "R020.bin"
    assert batch.pick_bin("V500R022C10SPC167", "default.bin", m)[0] == "2 - R022.bin"


def test_pick_bin_fallback_kalau_file_keluarga_tidak_ada():
    path, why = batch.pick_bin("V5R020C10S195", "default.bin", {"R022": "x.bin"})
    assert path == "default.bin"
    assert "R020" in why


# --- log CSV: migrasi kolom baru -----------------------------------------

def test_csv_append_migrasi_kolom_baru(tmp_path):
    root = str(tmp_path / "backup")
    batch._csv_append(root, {"host": "h1", "status": "ok"})
    batch._csv_append(root, {"host": "h2", "status": "ok", "software_final": "V5R020"})
    lines = (tmp_path / "backup" / "batch_log.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "host,status,software_final"
    assert len(lines) == 3
    assert lines[1] == "h1,ok,"
    assert lines[2] == "h2,ok,V5R020"


# --- regresi: step 5-8 tidak boleh stuck ---------------------------------

def _full_fakes(monkeypatch, calls, mode="2", software="V5R022C10S167"):
    monkeypatch.setattr(batch, "login_wait",
                        lambda host, timeout=180, quiet=False: (True, "cookie"))
    monkeypatch.setattr(batch, "get_device_info",
                        lambda host, cookie: dict(DEVINFO, SoftwareVersion=software))
    monkeypatch.setattr(batch, "download_config", lambda *a, **k: (True, "n/a"))
    monkeypatch.setattr(batch, "upload_xml_auto", lambda *a, **k: True)
    monkeypatch.setattr(batch, "upload_firmware", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(batch, "wait_for_up", lambda *a, **k: True)
    monkeypatch.setattr(batch, "wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(batch, "run_sequence", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(batch, "get_upport_mode", lambda host, cookie: mode)
    monkeypatch.setattr(batch, "time", NoSleepTime())

    def fake_wait_modem(hosts=None, poll=3, timeout=None, quiet=False):
        calls.setdefault("modem_timeouts", []).append(timeout)
        return "192.168.100.1"

    def fake_wait_telnet(hosts=None, timeout=300, poll=3, quiet=False):
        calls["telnet"] = calls.get("telnet", 0) + 1
        return "192.168.100.1"

    monkeypatch.setattr(batch, "wait_for_modem", fake_wait_modem)
    monkeypatch.setattr(batch, "wait_for_telnet", fake_wait_telnet)


def test_process_one_selesai_tanpa_stuck_di_equipmode(monkeypatch, tmp_path):
    """
    Regresi bug nyata: di equip mode web UI MATI, jadi menunggu `wait_for_modem()`
    (HTTP port 80) = stuck selamanya. Step 6 & 7 wajib menunggu lewat TELNET.
    """
    calls = {}
    _full_fakes(monkeypatch, calls)

    res = batch.process_one("192.168.100.1", "1_1010.xml", "2 - R022.bin",
                            backup_root=str(tmp_path), quiet=True)

    assert res["status"] == "ok", res
    assert res["upport_mode"] == "2"
    assert calls.get("telnet", 0) >= 2, "step 6 & 7 harus menunggu via telnet"
    assert all(t is not None for t in calls.get("modem_timeouts", [])), \
        "setiap wait_for_modem() wajib punya timeout"


def test_process_one_peringat_kalau_versi_firmware_tidak_berubah(monkeypatch, tmp_path):
    """Kalau flash tidak berefek (versi tetap sama), note harus memberi peringatan."""
    calls = {}
    _full_fakes(monkeypatch, calls, software="V5R020C10S195")

    res = batch.process_one("192.168.100.1", "1_1010.xml", "R020.bin",
                            backup_root=str(tmp_path), quiet=True)

    assert res["status"] == "ok"
    assert res["software"] == res["software_final"] == "V5R020C10S195"
    assert "tidak berubah" in res["note"]


def test_process_one_pakai_bin_map_sesuai_versi_modem(monkeypatch, tmp_path):
    calls = {}
    used = {}

    def fake_upload(host, cookie, path, verbose=False):
        used["bin"] = path
        return True, "ok"

    _full_fakes(monkeypatch, calls, software="V5R020C10S195")
    monkeypatch.setattr(batch, "upload_firmware", fake_upload)

    res = batch.process_one("192.168.100.1", "1_1010.xml", "default.bin",
                            backup_root=str(tmp_path), quiet=True,
                            bin_map={"R020": "R020.bin", "R022": "2 - R022.bin"})

    assert res["status"] == "ok"
    assert used["bin"] == "R020.bin"


def test_process_one_gagal_kalau_modem_tidak_kembali_setelah_equipmode(monkeypatch, tmp_path):
    """Dulu di sini batch menggantung. Sekarang harus failed dengan catatan jelas."""
    calls = {}
    state = {"n": 0}

    def fake_telnet(hosts=None, timeout=300, poll=3, quiet=False):
        state["n"] += 1
        # percobaan ke-1 = habis flash (lolos), setelah itu (equipmode) tidak kembali
        return "192.168.100.1" if state["n"] == 1 else None

    _full_fakes(monkeypatch, calls)
    monkeypatch.setattr(batch, "wait_for_telnet", fake_telnet)

    res = batch.process_one("192.168.100.1", "1_1010.xml", "2 - R022.bin",
                            backup_root=str(tmp_path), quiet=True)

    assert res["status"] == "failed"
    assert "equipmode" in res["note"]

