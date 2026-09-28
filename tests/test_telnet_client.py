"""Test klien telnet (steps/telnet_client.py) memakai socket & waktu palsu."""
import steps.telnet_client as tc
from helpers import FakeClock, FakeSock


def make_client(monkeypatch, verbose=False):
    c = tc.TelnetClient("192.168.100.1", verbose=verbose)
    c.sock = FakeSock()
    monkeypatch.setattr(tc, "time", FakeClock())
    return c


# --- filter negosiasi IAC -------------------------------------------------

def test_iac_will_dijawab_dont(monkeypatch):
    c = make_client(monkeypatch)
    assert c._handle_iac(b"\xff\xfb\x01hello") == b"hello"
    assert c.sock.sent == [b"\xff\xfe\x01"]


def test_iac_do_dijawab_wont(monkeypatch):
    c = make_client(monkeypatch)
    assert c._handle_iac(b"\xff\xfd\x03halo") == b"halo"
    assert c.sock.sent == [b"\xff\xfc\x03"]


def test_iac_wont_dan_dont_tidak_dijawab(monkeypatch):
    c = make_client(monkeypatch)
    assert c._handle_iac(b"\xff\xfc\x01abc") == b"abc"
    assert c._handle_iac(b"\xff\xfe\x01abc") == b"abc"
    assert c.sock.sent == []


def test_iac_iac_menjadi_satu_byte_255(monkeypatch):
    c = make_client(monkeypatch)
    assert c._handle_iac(b"a\xff\xffb") == b"a\xffb"
    assert c.sock.sent == []


def test_iac_terpotong_di_akhir_diabaikan(monkeypatch):
    c = make_client(monkeypatch)
    assert c._handle_iac(b"abc\xff") == b"abc"


def test_iac_teks_biasa_tidak_diubah(monkeypatch):
    c = make_client(monkeypatch)
    assert c._handle_iac(b"WAP>") == b"WAP>"


# --- expect ---------------------------------------------------------------

def test_expect_menemukan_pattern_dari_data_bertahap(monkeypatch):
    c = make_client(monkeypatch)
    chunks = iter(["Login: ", "Password: "])
    monkeypatch.setattr(c, "_recv_available", lambda: next(chunks, ""))
    pat, buf = c.expect(r"password", timeout=5)
    assert pat is not None
    assert "Password:" in buf


def test_expect_memakai_sisa_buffer_dari_panggilan_sebelumnya(monkeypatch):
    c = make_client(monkeypatch)
    c._buf = "WAP>"
    monkeypatch.setattr(c, "_recv_available", lambda: "")
    pat, buf = c.expect(r"WAP>", timeout=1)
    assert pat is not None
    assert "WAP>" in buf


def test_expect_timeout_mengembalikan_none_dan_menyimpan_buffer(monkeypatch):
    c = make_client(monkeypatch)
    monkeypatch.setattr(c, "_recv_available", lambda: "tidak ada prompt")
    pat, buf = c.expect(r"ZZZ", timeout=3)
    assert pat is None
    assert "tidak ada prompt" in buf
    assert "tidak ada prompt" in c._buf


def test_expect_menerima_beberapa_pattern_sekaligus(monkeypatch):
    c = make_client(monkeypatch)
    monkeypatch.setattr(c, "_recv_available", lambda: "SU_WAP>")
    pat, _ = c.expect(r"WAP>|SU_WAP>|#", timeout=2)
    assert pat is not None


# --- run_commands ---------------------------------------------------------

def test_run_commands_putus_saat_reboot_dianggap_sukses(monkeypatch):
    c = make_client(monkeypatch)
    monkeypatch.setattr(c, "_recv_available", lambda: "WAP>")

    def fake_send(line):
        if line == "reboot":
            raise OSError("koneksi diputus oleh modem")

    monkeypatch.setattr(c, "_send_line", fake_send)
    res = c.run_commands(["su", "reboot", "exit"], prompt_pattern=r"WAP>",
                         cmd_timeout=2, inter_delay=0)
    assert res["su"][0] is True
    assert res["reboot"][0] is True
    assert "koneksi putus" in res["reboot"][1]
    # setelah disconnect normal, sisa perintah tidak dijalankan
    assert "exit" not in res


def test_run_commands_error_biasa_ditandai_gagal(monkeypatch):
    c = make_client(monkeypatch)
    monkeypatch.setattr(c, "_recv_available", lambda: "WAP>")

    def fake_send(line):
        raise OSError("boom")

    monkeypatch.setattr(c, "_send_line", fake_send)
    res = c.run_commands(["sesuatu"], prompt_pattern=r"WAP>", cmd_timeout=2, inter_delay=0)
    assert res["sesuatu"][0] is False


def test_run_commands_tanpa_prompt_ditandai_gagal(monkeypatch):
    c = make_client(monkeypatch)
    monkeypatch.setattr(c, "_recv_available", lambda: "")
    monkeypatch.setattr(c, "_send_line", lambda line: None)
    res = c.run_commands(["sesuatu"], prompt_pattern=r"WAP>", cmd_timeout=2, inter_delay=0)
    assert res["sesuatu"][0] is False


def test_run_commands_semua_sukses(monkeypatch):
    c = make_client(monkeypatch)
    monkeypatch.setattr(c, "_recv_available", lambda: "WAP>")
    monkeypatch.setattr(c, "_send_line", lambda line: None)
    res = c.run_commands(["su", "shell"], prompt_pattern=r"WAP>", cmd_timeout=2, inter_delay=0)
    assert res == {"su": (True, "WAP>"), "shell": (True, "WAP>")}


# --- login ----------------------------------------------------------------

def test_login_berhasil(monkeypatch):
    c = make_client(monkeypatch)
    chunks = iter(["Login: ", "Password: ", "WAP>"])
    monkeypatch.setattr(c, "_recv_available", lambda: next(chunks, "WAP>"))
    assert c.login("root", "admin") is True


def test_login_ditolak_modem(monkeypatch):
    """False-negative login pernah jadi bug; pastikan penolakan asli tetap terdeteksi."""
    c = make_client(monkeypatch)
    chunks = iter(["Login: ", "Password: ", "incorrect password\r\nWAP>"])
    monkeypatch.setattr(c, "_recv_available", lambda: next(chunks, "WAP>"))
    assert c.login("root", "salah") is False


def test_login_tanpa_prompt_tetap_mengirim_kredensial(monkeypatch):
    """Prompt tidak terlihat: tetap kirim user/password, lalu sukses kalau prompt muncul."""
    c = make_client(monkeypatch)
    chunks = iter(["", "", "WAP>"])
    monkeypatch.setattr(c, "_recv_available", lambda: next(chunks, "WAP>"))
    assert c.login("root", "admin") is True
    # user + password harus tetap terkirim ke socket
    assert b"root" in b"".join(c.sock.sent)
    assert b"admin" in b"".join(c.sock.sent)
