"""
Test parsing & helper murni steps/modem_http.py - TANPA modem.

Fokus pada logika yang pernah bikin bug nyata di lapangan:
  * RequestToken yang OPSIONAL (ada di firmware lama, tidak ada di R022)
  * `_form_action` yang salah cocok: cfgfileupload.cgi vs ptvdfcfgfileupload.cgi
"""
import pytest

from steps import modem_http as mh


# HTML yang disederhanakan dari halaman firmware nyata.
R022_FORM_HTML = """
<html><body>
<form action="cfgfileupload.cgi?RequestFile=html/ssmp/reset/reset.asp&amp;FileType=config"
      name="fr_uploadSetting" method="post" enctype="multipart/form-data">
  <input type="hidden" name="onttoken" id="hwonttoken" value="DEADBEEFCAFE1234">
  <input type="hidden" name="onttoken" id="egvdfonttoken" value="SECONDTOKEN">
  <input type="file" name="browse">
</form>
<form action="ptvdfcfgfileupload.cgi?FileType=config" name="fr_uploadPtvdf" method="post"></form>
</body></html>
"""

ONLY_PTVDF_HTML = '<form action="ptvdfcfgfileupload.cgi?FileType=config" name="fr_x"></form>'


# --- _extract_tokens ------------------------------------------------------

def test_extract_tokens_r022_tanpa_requesttoken():
    """Firmware V5R022: tidak ada RequestToken, hanya onttoken. Ini pernah bikin error."""
    rt, ont = mh._extract_tokens(R022_FORM_HTML)
    assert rt is None
    assert ont == "DEADBEEFCAFE1234"


def test_extract_tokens_requesttoken_dari_form_action():
    html = '<form action="cfgfileupload.cgi?RequestToken=9f8e7d6c5b4a39281706&amp;FileType=config"></form>'
    rt, _ = mh._extract_tokens(html)
    assert rt == "9f8e7d6c5b4a39281706"


def test_extract_tokens_requesttoken_dari_hidden_input():
    html = '<input type="hidden" name="RequestToken" value="ABCD1234EF567890">'
    rt, _ = mh._extract_tokens(html)
    assert rt == "ABCD1234EF567890"


def test_extract_tokens_hwonttoken_id_saja():
    rt, ont = mh._extract_tokens('<input type="hidden" id="hwonttoken" value="TOKENONLY">')
    assert rt is None
    assert ont == "TOKENONLY"


def test_extract_tokens_egvdfonttoken_sebagai_fallback():
    _, ont = mh._extract_tokens('<input type="hidden" id="egvdfonttoken" value="EGVDF">')
    assert ont == "EGVDF"


def test_extract_tokens_html_kosong():
    assert mh._extract_tokens("") == (None, "")


# --- _form_action ---------------------------------------------------------

def test_form_action_prioritas_form_bernama():
    got = mh._form_action(R022_FORM_HTML, "cfgfileupload.cgi", "fr_uploadSetting")
    assert got.startswith("cfgfileupload.cgi?RequestFile=")
    assert "FileType=config" in got


def test_form_action_tanpa_nama_form_tetap_ketemu():
    got = mh._form_action(R022_FORM_HTML, "cfgfileupload.cgi")
    assert got.startswith("cfgfileupload.cgi?")


def test_form_action_tidak_salah_cocok_dengan_ptvdf():
    """REGRESI: 'cfgfileupload.cgi' tidak boleh cocok dengan 'ptvdfcfgfileupload.cgi'."""
    assert mh._form_action(ONLY_PTVDF_HTML, "cfgfileupload.cgi") is None
    # ...tapi kalau memang dicari ptvdf-nya, harus ketemu
    assert mh._form_action(ONLY_PTVDF_HTML, "ptvdfcfgfileupload.cgi") is not None


def test_form_action_tanpa_form():
    assert mh._form_action("<html><body>tidak ada form</body></html>", "cfgfileupload.cgi") is None


# --- _upload_path ---------------------------------------------------------

def test_upload_path_relatif_menjadi_absolut():
    html = '<form action="cfgfileupload.cgi?FileType=config" name="fr_uploadSetting"></form>'
    got = mh._upload_path(html, "cfgfileupload.cgi", "/html/ssmp/cfgfile/cfgfile.asp",
                          "fr_uploadSetting", "/fallback.cgi")
    assert got == "/html/ssmp/cfgfile/cfgfileupload.cgi?FileType=config"


def test_upload_path_absolut_dibiarkan():
    html = '<form action="/html/ssmp/fireware/Firmwareupload.cgi?FileType=image" name="fr_uploadImage"></form>'
    got = mh._upload_path(html, "Firmwareupload.cgi", "/html/ssmp/fireware/firmware.asp",
                          "fr_uploadImage", "/fallback.cgi")
    assert got == "/html/ssmp/fireware/Firmwareupload.cgi?FileType=image"


def test_upload_path_amp_entity_diurai():
    html = '<form action="/a/b.cgi?x=1&amp;y=2" name="fr"></form>'
    assert mh._upload_path(html, "b.cgi", "/p/q.asp", "fr", "z") == "/a/b.cgi?x=1&y=2"


def test_upload_path_pakai_fallback_kalau_form_tidak_ada():
    got = mh._upload_path("<html></html>", "cfgfileupload.cgi", "/a/b.asp", "fr", "/fallback.cgi")
    assert got == "/fallback.cgi"


# --- _multipart -----------------------------------------------------------

def test_multipart_struktur_tombol_dan_file():
    body, boundary = mh._multipart({"onttoken": "T123"}, "browse", "1_1010.xml", b"<xml/>")
    b = boundary.encode()
    assert body.startswith(b"--" + b + b"\r\n")
    assert b'name="onttoken"' in body
    assert b"T123" in body
    assert b'name="browse"; filename="1_1010.xml"' in body
    assert b"<xml/>" in body
    assert body.endswith(b"\r\n--" + b + b"--\r\n")


def test_multipart_tanpa_field_tambahan():
    body, boundary = mh._multipart(None, "browse", "fw.bin", b"\x00\x01")
    assert b'filename="fw.bin"' in body
    assert b"\x00\x01" in body


# --- _unescape_js / short_serial -----------------------------------------

def test_unescape_js_mengubah_escape_hex():
    assert mh._unescape_js(r"a\x2eb\x2d") == "a.b-"


@pytest.mark.parametrize("raw, expected", [
    ("485754439A1892AF", "HWTC9A1892AF"),
    ("485754439a1892af", "HWTC9A1892AF"),
    ("HWTC9A1892AF", "HWTC9A1892AF"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_short_serial(raw, expected):
    assert mh.short_serial(raw) == expected


def test_short_serial_16_karakter_bukan_hex_dibiarkan():
    assert mh.short_serial("ZZZZZZZZZZZZZZZZ") == "ZZZZZZZZZZZZZZZZ"


# --- pembacaan halaman (pakai _get_page palsu) ----------------------------

DEVINFO_HTML = (
    "<html>" + ("x" * 1200) + "\n"
    'new stDeviceInfo("", "485754439A1892AF", "1.0", "V5R022C10S167", "EG8145V5",'
    ' "HWTC", "2022-01-01", "08:02:05:E9:79:34", "deskripsi", "", "alias");\n'
    "</html>"
)


def test_get_device_info_membaca_semua_field(monkeypatch):
    monkeypatch.setattr(mh, "_get_page", lambda *a, **k: (200, DEVINFO_HTML))
    info = mh.get_device_info("192.168.100.1", "cookie")
    assert info["SerialNumber"] == "485754439A1892AF"
    assert info["ModelName"] == "EG8145V5"
    assert info["SoftwareVersion"] == "V5R022C10S167"
    assert info["Mac"] == "08:02:05:E9:79:34"
    assert mh.short_serial(info["SerialNumber"]) == "HWTC9A1892AF"


def test_get_device_info_halaman_terlalu_pendek(monkeypatch):
    monkeypatch.setattr(mh, "_get_page", lambda *a, **k: (200, "<html>kecil</html>"))
    assert mh.get_device_info("h", "cookie") is None


def test_get_device_info_tanpa_stdeviceinfo(monkeypatch):
    monkeypatch.setattr(mh, "_get_page", lambda *a, **k: (200, "y" * 1200))
    assert mh.get_device_info("h", "cookie") is None


def test_get_upport_mode_epon(monkeypatch):
    html = '<script>new stConfigPort("Optical", "Optical", "2");</script>'
    monkeypatch.setattr(mh, "_get_page", lambda *a, **k: (200, html))
    assert mh.get_upport_mode("h", "cookie") == "2"


def test_get_upport_mode_bukan_http_200(monkeypatch):
    monkeypatch.setattr(mh, "_get_page", lambda *a, **k: (404, ""))
    assert mh.get_upport_mode("h", "cookie") is None


def test_get_upport_mode_tanpa_stconfigport(monkeypatch):
    monkeypatch.setattr(mh, "_get_page", lambda *a, **k: (200, "<html>halaman lain</html>"))
    assert mh.get_upport_mode("h", "cookie") is None
