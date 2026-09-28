"""Test lapisan tampilan (steps/ui.py) - murni teks, tidak menyentuh logika/method."""
import pytest

from steps import ui


# --- glyph / warna --------------------------------------------------------

def test_sym_ascii_dalam_mode_plain():
    assert ui.sym("check") == "v"
    assert ui.sym("cross") == "x"
    assert ui.sym("h") == "="
    assert ui.sym("v") == "|"


def test_paint_tanpa_warna_mengembalikan_teks_apa_adanya():
    assert ui.paint("halo", "red", bold=True) == "halo"


def test_vis_len_mengabaikan_kode_ansi():
    assert ui.vis_len("\033[36mabc\033[0m") == 3
    assert ui.vis_len("abc") == 3


def test_pad_menambah_spasi_sampai_lebar_target():
    assert ui.pad("ab", 5) == "ab   "
    assert ui.pad("abcdef", 3) == "abcdef"


# --- progress / step ------------------------------------------------------

def test_step_total_delapan():
    assert ui.STEP_TOTAL == 8
    assert len(ui._STEP_NAMES) == 8


def test_progress_bar_bentuk_dan_persentase():
    out = ui.progress(4, 8, width=10)
    assert "[#####.....]" in out
    assert "4/8" in out
    assert "50%" in out


def test_progress_aman_saat_total_nol():
    out = ui.progress(0, 0, width=4)
    assert "0/0" in out


@pytest.mark.parametrize("n, total, expected_bar", [
    (0, 8, "[........]"),
    (4, 8, "[####....]"),
    (8, 8, "[########]"),
])
def test_progress_isi_bar_sesuai_proporsi(n, total, expected_bar):
    assert expected_bar in ui.progress(n, total, width=8)


def test_step_plain_menampilkan_nomor_dan_nama_step(capsys):
    ui.step(3)
    out = capsys.readouterr().out
    assert "[STEP 3/8]" in out
    assert "BACKUP CONFIG" in out


def test_step_plain_judul_kustom(capsys):
    ui.step(1, "JUDUL SENDIRI")
    assert "JUDUL SENDIRI" in capsys.readouterr().out


# --- log / alert / banner -------------------------------------------------

def test_log_plain_mencetak_pesan(capsys):
    ui.log("halo dunia", "OK")
    out = capsys.readouterr().out
    assert "halo dunia" in out
    assert "OK" in out


def test_alert_plain_mencetak_judul_dan_semua_baris(capsys):
    ui.alert(["baris satu", "baris dua"], title="CABUT MODEM")
    out = capsys.readouterr().out
    assert "CABUT MODEM" in out
    assert "baris satu" in out
    assert "baris dua" in out


def test_banner_plain(capsys):
    ui.banner("SUBJUDUL")
    out = capsys.readouterr().out
    assert "5v5 FLASHER" in out
    assert "SUBJUDUL" in out


# --- tabel ----------------------------------------------------------------

def test_table_tanpa_baris_tidak_mencetak_apa_pun(capsys):
    ui.table([])
    assert capsys.readouterr().out == ""


def test_table_mencetak_header_dan_isi(capsys):
    rows = [["#1", "HWTC9A1892AF", "EG8145V5", "ok", "EPON aktif"]]
    ui.table(rows, headers=("#", "SERIAL", "MODEL", "STATUS", "KETERANGAN"))
    out = capsys.readouterr().out
    assert "SERIAL" in out
    assert "HWTC9A1892AF" in out
    assert "EG8145V5" in out
    assert "EPON aktif" in out


def test_table_menyeimbangkan_jumlah_kolom(capsys):
    # baris pertama 2 kolom, baris kedua 4 kolom -> tidak boleh error
    ui.table([["a", "b"], ["1", "2", "3", "4"]])
    assert "a" in capsys.readouterr().out
