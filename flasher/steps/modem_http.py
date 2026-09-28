"""
modem_http.py - Login web modem + upload config XML
Tanpa dependensi eksternal (urllib stdlib), kompatibel Linux + Termux.
Menggantikan upload manual via Settings > Maintenance > Configuration File (step.md:11)
"""
import base64
import os
import re
import time
import http.client
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET

try:  # lapisan tampilan (opsional; kalau gagal, tetap jalan apa adanya)
    from steps import ui as _ui
except ImportError:
    try:
        from . import ui as _ui
    except ImportError:
        _ui = None


CREDENTIALS = [
    ("Epadmin", "adminEp", "192.168.18.1"),
    ("telecomadmin", "admintelecom", "192.168.100.1"),
]

DEFAULT_TIMEOUT = 10


def _log(msg, level="INFO"):
    """Cetak log. Tampilan (warna/ikon) ditangani steps/ui.py bila tersedia."""
    if _ui is not None:
        _ui.log(msg, level)
        return
    prefix = {"INFO": "[*]", "OK": "[OK]", "WARN": "[!]", "ERR": "[ERR]"}
    print(f"{prefix.get(level, '[*]')} {msg}")


def _http_request(host, method, path, headers=None, data=None, cookies=None, timeout=DEFAULT_TIMEOUT):
    """Low-level request via http.client agar bisa reuse koneksi (penting untuk token)."""
    if headers is None:
        headers = {}
    conn = http.client.HTTPConnection(host, timeout=timeout)
    try:
        if cookies:
            headers["Cookie"] = cookies
        # ensure Host header
        if "Host" not in headers:
            headers["Host"] = host
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        # collect Set-Cookie
        set_cookie = resp.getheader("Set-Cookie", "")
        return resp.status, resp.getheaders(), body, set_cookie
    finally:
        conn.close()


def _persistent_login(host, username, password, verbose=True):
    """
    Login sesuai riset huawei-ont-mcp:
      POST /asp/GetRandCount.asp (no body) -> token
      POST /login.cgi on SAME TCP connection with token
    Fallback ke login sederhana jika endpoint tidak ada.
    Return: (success, cookie_str, method_used)
    """
    def vlog(m, lv="INFO"):
        if verbose:
            _log(m, lv)

    # Try persistent connection approach (needed for token-bound login)
    try:
        conn = http.client.HTTPConnection(host, timeout=DEFAULT_TIMEOUT)
        # Step 1: GetRandCount
        vlog(f"Mencoba login {username}@{host} (metode token persist)...")
        conn.request("POST", "/asp/GetRandCount.asp", body=b"", headers={"Host": host, "Content-Length": "0"})
        resp = conn.getresponse()
        token_body = resp.read()
        set_cookie1 = resp.getheader("Set-Cookie", "")
        # token may have BOM
        try:
            token = token_body.decode("utf-8", errors="ignore").strip().lstrip("\ufeff").strip()
        except Exception:
            token = ""
        # step 2: login.cgi on same connection
        b64pass = base64.b64encode(password.encode()).decode()
        form = f"UserName={urllib.parse.quote(username)}&PassWord={urllib.parse.quote(b64pass)}&Language=english&x.X_HW_Token={urllib.parse.quote(token)}"
        headers2 = {
            "Host": host,
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "Cookie=body:Language:english:id=-1",
        }
        if set_cookie1:
            # keep first cookie if any, but spec says only send fixed cookie on second request
            pass
        conn.request("POST", "/login.cgi", body=form.encode(), headers=headers2)
        resp2 = conn.getresponse()
        body2 = resp2.read()
        set_cookie2 = resp2.getheader("Set-Cookie", "")
        status2 = resp2.status
        conn.close()

        # Success if status 200 and Set-Cookie contains sid or Location redirect
        body2_str = body2.decode(errors="ignore")
        if set_cookie2 and ("sid" in set_cookie2.lower() or "cookie=" in set_cookie2.lower()):
            vlog(f"Login token OK ke {host} ({username}), cookie: {set_cookie2[:80]}", "OK")
            return True, set_cookie2, "token-persist"
        if status2 in (200, 302) and ("success" in body2_str.lower() or "index" in body2_str.lower() or len(body2_str) < 3000):
            # some firmwares return 200 with js redirect; check not error
            if "error" not in body2_str.lower() or "sid" in body2_str.lower():
                cookie = set_cookie2 if set_cookie2 else set_cookie1
                if cookie:
                    vlog(f"Login token OK (heuristik) ke {host}", "OK")
                    return True, cookie, "token-persist"
        vlog(f"Login token gagal status={status2} body={body2_str[:200]!r}", "WARN")
        # fall through to fallback
    except Exception as e:
        vlog(f"Login token error: {e}", "WARN")
        try:
            conn.close()
        except Exception:
            pass

    # Fallback 1: simple POST /login.cgi without token persistence
    try:
        vlog("Coba fallback login sederhana...")
        b64pass = base64.b64encode(password.encode()).decode()
        form = urllib.parse.urlencode({"UserName": username, "PassWord": b64pass}).encode()
        status, headers, body, set_cookie = _http_request(host, "POST", "/login.cgi",
            headers={"Content-Type": "application/x-www-form-urlencoded"}, data=form)
        body_str = body.decode(errors="ignore")
        if set_cookie and "sid" in set_cookie.lower():
            vlog(f"Fallback login OK ke {host}", "OK")
            return True, set_cookie, "fallback-simple"
        if status in (200, 302) and "error" not in body_str.lower()[:500]:
            if set_cookie:
                vlog(f"Fallback login OK (heuristik) ke {host}", "OK")
                return True, set_cookie, "fallback-simple"
        vlog(f"Fallback gagal status={status} body={body_str[:200]!r}", "WARN")
    except Exception as e:
        vlog(f"Fallback error: {e}", "WARN")

    # Fallback 2: GET /login with basic auth style (some ONT use HTTP basic)
    try:
        vlog("Coba fallback basic-auth probe...")
        status, headers, body, set_cookie = _http_request(host, "GET", "/", headers={})
        if status == 401:
            # try basic auth
            cred = base64.b64encode(f"{username}:{password}".encode()).decode()
            status2, _, body2, set_cookie2 = _http_request(host, "GET", "/", headers={"Authorization": f"Basic {cred}"})
            if status2 == 200:
                vlog(f"Basic-auth OK ke {host}", "OK")
                return True, set_cookie2, "basic-auth"
    except Exception as e:
        vlog(f"Basic-auth probe error: {e}", "WARN")

    return False, "", "none"


def detect_modem(hosts=None, timeout=3, verbose=True):
    """Cek modem hidup di daftar host (default step.md: 192.168.18.1 dan 192.168.100.1)."""
    if hosts is None:
        hosts = ["192.168.18.1", "192.168.100.1"]
    found = []
    for h in hosts:
        try:
            conn = http.client.HTTPConnection(h, timeout=timeout)
            conn.request("GET", "/", headers={"Host": h})
            resp = conn.getresponse()
            body = resp.read(2048)
            status = resp.status
            conn.close()
            # consider 200/302/401 as alive (web UI present)
            if status in (200, 302, 401, 403):
                if verbose:
                    _log(f"Modem terdeteksi di {h} (HTTP {status})", "OK")
                found.append(h)
            else:
                if verbose:
                    _log(f"{h} HTTP {status}", "WARN")
        except Exception as e:
            if verbose:
                _log(f"{h} tidak merespon: {e}", "WARN")
    return found


def try_login_any_host(hosts=None, credentials=None, verbose=True):
    """Coba semua kombinasi host+credential, return (host, user, cookie) pertama yang sukses."""
    if hosts is None:
        hosts = ["192.168.18.1", "192.168.100.1"]
    if credentials is None:
        credentials = [("Epadmin", "adminEp"), ("telecomadmin", "admintelecom"), ("admin", "admin"), ("root", "admin")]
    for host in hosts:
        for user, pwd in credentials:
            ok, cookie, method = _persistent_login(host, user, pwd, verbose=verbose)
            if ok:
                return host, user, pwd, cookie, method
    return None


# ---------------------------------------------------------------------------
# Endpoint ASLI Huawei SSMP (terverifikasi pada EG8145V5, firmware 2022):
#   Halaman config : /html/ssmp/cfgfile/cfgfile.asp
#   Upload config  : POST /html/ssmp/cfgfile/cfgfileupload.cgi
#                    ?RequestFile=html/ssmp/reset/reset.asp&FileType=config
#                    &RequestToken=<dari form action>
#                    field: onttoken + browse(file)
#   Halaman FW     : /html/ssmp/fireware/firmware.asp
#   Upload FW      : POST /html/ssmp/fireware/Firmwareupload.cgi
#                    ?RequestFile=/html/ssmp/reset/reset.asp&FileType=image
#                    field: onttoken + browse(file)
#   Upport (set)   : POST /html/ssmp/mainupportcfg/set.cgi
#                    x.X_HW_UpPortMode=<1 GPON|2 EPON|4 XPON|3 LAN|8 WIFI>
#                    x.X_HW_UpPortID=0x102001  x.X_HW_MainUpPort=Optical
#                    x.X_HW_Token=<onttoken dari halaman>
# ---------------------------------------------------------------------------
CFG_PAGE = "/html/ssmp/cfgfile/cfgfile.asp"
FW_PAGE = "/html/ssmp/fireware/firmware.asp"
UPPORT_PAGE = "/html/ssmp/mainupportcfg/mainupportconfig.asp"


def _get_page(host, cookie, path, timeout=15):
    hdrs = {"Host": host, "User-Agent": "Mozilla/5.0"}
    if cookie:
        hdrs["Cookie"] = cookie
    status, headers, body, _ = _http_request(host, "GET", path, headers=hdrs, timeout=timeout)
    return status, body.decode("utf-8", "ignore")


def _extract_tokens(html):
    """
    Ambil token dari halaman.
      - RequestToken : OPSIONAL. Ada di firmware lama (di form action / JS),
                       TIDAK ADA di firmware R022 baru.
      - onttoken     : WAJIB. hidden field 'onttoken' / id 'hwonttoken'.
    Return: (request_token|None, onttoken)
    """
    rt = None
    m = re.search(r"RequestToken=([0-9a-fA-F]{16,})", html)
    if m:
        rt = m.group(1)
    else:
        m = re.search(r'<input[^>]*name=["\']?RequestToken["\']?[^>]*>', html, re.I)
        if m:
            v = re.search(r'value=["\']([^"\']+)["\']', m.group(0))
            if v:
                rt = v.group(1)

    ont = (re.search(r'name="onttoken"[^>]*value="([^"]*)"', html)
           or re.search(r'id="hwonttoken"[^>]*value="([^"]*)"', html)
           or re.search(r'id="egvdfonttoken"[^>]*value="([^"]*)"', html)
           or re.search(r'name="onttoken"[^>]*value=\'([^\']*)\'', html))
    return rt, (ont.group(1) if ont else "")


def _form_action(html, cgi_name, form_name=None):
    """
    Ambil action dari <form ...> yang cocok.
    Prioritas: form dengan name/id tertentu (mis. 'fr_uploadSetting'),
    lalu fallback: action yang mengandung cgi_name (dengan batas kata,
    supaya 'cfgfileupload.cgi' tidak tertukar dengan 'ptvdfcfgfileupload.cgi').
    """
    tags = re.findall(r"<form[^>]*>", html, re.I)
    if form_name:
        for tag in tags:
            if form_name in tag:
                m = re.search(r'action=["\']([^"\']+)["\']', tag, re.I)
                if m:
                    return m.group(1)
    pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(cgi_name))
    for tag in tags:
        m = re.search(r'action=["\']([^"\']+)["\']', tag, re.I)
        if m and pat.search(m.group(1)):
            return m.group(1)
    return None


def _upload_path(page, cgi_name, page_path, form_name, fallback):
    """
    Tentukan URL upload dari form action halaman (adaptif antar-firmware).
    Relatif -> dijadikan absolut terhadap folder halaman.
    """
    act = _form_action(page, cgi_name, form_name)
    if not act:
        return fallback
    act = act.replace("&amp;", "&")
    if act.startswith("/"):
        return act
    base = page_path.rsplit("/", 1)[0]
    return f"{base}/{act}"


def _multipart(fields, file_field, filename, data, content_type="application/octet-stream"):
    boundary = "----WebKitFormBoundaryFlasher5v5001"
    parts = []
    for k, v in (fields or {}).items():
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        parts.append(str(v).encode())
        parts.append(b"\r\n")
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode())
    parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


DEVINFO_PAGE = "/html/ssmp/deviceinfo/deviceinfo.asp"


def _unescape_js(s):
    """Ubah '\\x2e' jadi '.' (escape gaya Huawei)."""
    return re.sub(r"\\x([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), s)


def short_serial(sn):
    """SN 16-hex (485754439A1892AF) -> bentuk 12-char (HWTC9A1892AF)."""
    if not sn:
        return "unknown"
    if len(sn) == 16 and re.fullmatch(r"[0-9A-Fa-f]{16}", sn):
        try:
            vendor = bytes.fromhex(sn[:8]).decode("ascii", "ignore")
            return (vendor + sn[8:]).upper()
        except Exception:
            return sn.upper()
    return sn


def get_device_info(host, cookie, verbose=False):
    """
    Baca identitas ONT dari halaman deviceinfo:
      new stDeviceInfo(domain, SerialNumber, HardwareVersion, SoftwareVersion,
                       ModelName, VendorID, ReleaseTime, Mac, Description,
                       ManufactureInfo, DeviceAlias)
    Return dict atau None.
    """
    st, page = _get_page(host, cookie, DEVINFO_PAGE)
    if st != 200 or len(page) < 1000:
        return None
    m = re.search(r"new\s+stDeviceInfo\(([^)]*)\)", page)
    if not m:
        return None
    args = [_unescape_js(a) for a in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))]
    keys = ["domain", "SerialNumber", "HardwareVersion", "SoftwareVersion",
            "ModelName", "VendorID", "ReleaseTime", "Mac", "Description",
            "ManufactureInfo", "DeviceAlias"]
    info = dict(zip(keys, args))
    if verbose:
        _log(f"Info: {info.get('ModelName')} SN={info.get('SerialNumber')} "
             f"({short_serial(info.get('SerialNumber'))}) SW={info.get('SoftwareVersion')} "
             f"MAC={info.get('Mac')}")
    return info


def get_upport_mode(host, cookie, verbose=False):
    """Baca mode upstream aktif dari halaman upport. 1=GPON 2=EPON 3=LAN 4=XPON 8=WIFI."""
    st, page = _get_page(host, cookie, UPPORT_PAGE)
    if st != 200:
        return None
    m = re.search(r"new\s+stConfigPort\(([^)]*)\)", page)
    if not m:
        return None
    parts = re.findall(r'"([^"]*)"', m.group(1))
    if len(parts) >= 3:
        if verbose:
            _log(f"Upport mode aktif = {parts[2]} (main port {parts[1]})")
        return parts[2]
    return None


def upload_config_xml(host, cookie, xml_path, verbose=True):
    """
    Upload Configuration File via endpoint asli (step.md:11).
      POST /html/ssmp/cfgfile/cfgfileupload.cgi?...&RequestToken=<tok>
    Return: (success, response_text)
    """
    if not os.path.isfile(xml_path):
        _log(f"File tidak ditemukan: {xml_path}", "ERR")
        return False, "file not found"

    status, page = _get_page(host, cookie, CFG_PAGE)
    if status != 200 or len(page) < 1000:
        _log(f"Tidak bisa buka {CFG_PAGE} (HTTP {status}, len {len(page)}). Session mungkin expired.", "ERR")
        return False, f"page HTTP {status}"
    token, onttoken = _extract_tokens(page)
    if not onttoken:
        _log("onttoken tidak ditemukan di halaman config", "ERR")
        return False, "no onttoken"
    if verbose:
        _log(f"Token cfgfile: RequestToken={(token[:16] + '...') if token else '(tidak dipakai firmware ini)'}"
             f" onttoken={onttoken[:16]}...")

    with open(xml_path, "rb") as f:
        data = f.read()
    body, boundary = _multipart({"onttoken": onttoken}, "browse",
                                os.path.basename(xml_path), data, "text/xml")
    path = _upload_path(
        page, "cfgfileupload.cgi", CFG_PAGE, "fr_uploadSetting",
        "/html/ssmp/cfgfile/cfgfileupload.cgi?RequestFile=html/ssmp/reset/reset.asp&FileType=config")
    if token and "RequestToken=" not in path:
        path += f"&RequestToken={token}"
    headers = {
        "Host": host,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "Referer": f"http://{host}{CFG_PAGE}",
    }
    if cookie:
        headers["Cookie"] = cookie
    if verbose:
        _log(f"POST cfgfileupload.cgi ({len(data)} byte) ...")
    status, resp_headers, resp_body, _ = _http_request(host, "POST", path, headers=headers, data=body, timeout=90)
    text = resp_body.decode("utf-8", "ignore")
    if verbose:
        _log(f"HTTP {status} respons: {text[:300]!r}")
    if status not in (200, 302):
        return False, text
    if re.search(r"error|fail|invalid|not\s+support", text, re.I):
        _log("Modem menolak file (kata kunci error di respons)", "WARN")
        return False, text
    return True, text


def download_config(host, cookie, out_path, verbose=True):
    """
    Backup/download config berjalan (setara tombol 'Download Configuration File').
      POST /html/ssmp/cfgfile/cfgfiledown.cgi?&RequestFile=html/ssmp/cfgfile/cfgfile.asp
      body: x.X_HW_Token=<onttoken>
    Return: (success, info_str)
    """
    status, page = _get_page(host, cookie, CFG_PAGE)
    if status != 200 or len(page) < 1000:
        return False, f"page HTTP {status}"
    _, onttoken = _extract_tokens(page)
    body = urllib.parse.urlencode({"x.X_HW_Token": onttoken}).encode()
    path = "/html/ssmp/cfgfile/cfgfiledown.cgi?&RequestFile=html/ssmp/cfgfile/cfgfile.asp"
    headers = {
        "Host": host,
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
        "Referer": f"http://{host}{CFG_PAGE}",
    }
    if cookie:
        headers["Cookie"] = cookie
    if verbose:
        _log(f"POST cfgfiledown.cgi (token {onttoken[:16]}...) ...")
    status, rsp_h, rsp_b, _ = _http_request(host, "POST", path, headers=headers, data=body, timeout=90)
    disp = ""
    for k, v in rsp_h:
        if k.lower() == "content-disposition":
            disp = v
    if verbose:
        _log(f"HTTP {status} len={len(rsp_b)} content-disposition={disp!r} magic={rsp_b[:8]!r}")
    if status not in (200, 302):
        return False, f"HTTP {status}"
    if len(rsp_b) < 100 or b"not found" in rsp_b[:200].lower():
        return False, f"respons terlalu kecil/error ({len(rsp_b)} byte)"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(rsp_b)
    return True, f"{len(rsp_b)} byte -> {out_path}"


def upload_firmware(host, cookie, bin_path, verbose=True):
    """
    Upload FIRMWARE (.bin) via web UI (halaman Firmware Upgrade).
    Ini kandidat pengganti Fase 2 (UDP multicast) - belum tentu modem
    menerima file non-firmware seperti '2 - R022.bin'.
    Return: (success, response_text)
    """
    if not os.path.isfile(bin_path):
        _log(f"File tidak ditemukan: {bin_path}", "ERR")
        return False, "file not found"
    status, page = _get_page(host, cookie, FW_PAGE)
    if status != 200 or len(page) < 500:
        _log(f"Tidak bisa buka {FW_PAGE} (HTTP {status})", "ERR")
        return False, f"page HTTP {status}"
    _, onttoken = _extract_tokens(page)
    if not onttoken:
        _log("onttoken tidak ditemukan di halaman firmware", "ERR")
        return False, "no onttoken"
    with open(bin_path, "rb") as f:
        data = f.read()
    body, boundary = _multipart({"onttoken": onttoken}, "browse",
                                os.path.basename(bin_path), data, "application/octet-stream")
    path = _upload_path(
        page, "Firmwareupload.cgi", FW_PAGE, "fr_uploadImage",
        "/html/ssmp/fireware/Firmwareupload.cgi?RequestFile=/html/ssmp/reset/reset.asp&FileType=image")
    headers = {
        "Host": host,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
        "Referer": f"http://{host}{FW_PAGE}",
    }
    if cookie:
        headers["Cookie"] = cookie
    if verbose:
        _log(f"POST Firmwareupload.cgi ({len(data)} byte) ...")
    status, resp_headers, resp_body, _ = _http_request(host, "POST", path, headers=headers, data=body, timeout=180)
    text = resp_body.decode("utf-8", "ignore")
    if verbose:
        _log(f"HTTP {status} respons: {text[:300]!r}")
    if status not in (200, 302):
        return False, text
    if re.search(r"error|fail|invalid|not\s+support|illegal", text, re.I):
        _log("Modem menolak firmware (kata kunci error di respons)", "WARN")
        return False, text
    return True, text


def set_upport_mode_http(host, cookie, mode, upportid=None, reboot=True, verbose=True):
    """
    Set upstream port mode lewat web UI (setara telnet 'set upport mode N upportid 0x...').
      mode: 1=GPON, 2=EPON, 4=XPON, 3=LAN, 8=WIFI
    Return: (success, response_text)
    """
    MAP_ID = {1: "0x102001", 2: "0x102001", 4: "0x102001", 3: "0x00000002", 8: "0x00304008"}
    if upportid is None:
        upportid = MAP_ID.get(int(mode), "0x102001")
    status, page = _get_page(host, cookie, UPPORT_PAGE)
    if status != 200 or len(page) < 1000:
        _log(f"Tidak bisa buka {UPPORT_PAGE} (HTTP {status})", "ERR")
        return False, f"page HTTP {status}"
    _, onttoken = _extract_tokens(page)
    main_up = "Optical" if int(mode) in (1, 2, 4) else "LAN"
    params = [
        ("x.X_HW_UpPortMode", str(mode)),
        ("x.X_HW_UpPortID", str(upportid)),
        ("x.X_HW_MainUpPort", main_up),
        ("x.X_HW_Token", onttoken),
    ]
    if reboot:
        params.append(("y.InternetGatewayDevice.X_HW_DEBUG.SMP.DM.ResetBoard", ""))
    body = urllib.parse.urlencode(params).encode()
    path = ("/html/ssmp/mainupportcfg/set.cgi?"
            "&x=InternetGatewayDevice.DeviceInfo"
            "&RequestFile=html/ssmp/mainupportcfg/mainupportconfig.asp")
    headers = {
        "Host": host,
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
        "Referer": f"http://{host}{UPPORT_PAGE}",
    }
    if cookie:
        headers["Cookie"] = cookie
    if verbose:
        _log(f"POST set.cgi mode={mode} upportid={upportid} main={main_up} ...")
    status, resp_headers, resp_body, _ = _http_request(host, "POST", path, headers=headers, data=body, timeout=60)
    text = resp_body.decode("utf-8", "ignore")
    if verbose:
        _log(f"HTTP {status} respons: {text[:300]!r}")
    if status not in (200, 302):
        return False, text
    if re.search(r"error|fail|invalid", text, re.I):
        return False, text
    return True, text


def login_host(host, verbose=True):
    """Login ke satu host tertentu (Epadmin lalu telecomadmin). Return (ok, cookie)."""
    creds = [("Epadmin", "adminEp"), ("telecomadmin", "admintelecom")]
    if host == "192.168.100.1":
        creds = [("telecomadmin", "admintelecom"), ("Epadmin", "adminEp")]
    for user, pwd in creds:
        ok, cookie, method = _persistent_login(host, user, pwd, verbose=verbose)
        if ok:
            if verbose:
                _log(f"Login sukses {user}@{host} via {method}", "OK")
            return True, cookie
    return False, ""


def upload_xml_auto(xml_path, hosts=None, verbose=True):
    """High-level: auto detect host+login lalu upload config XML."""
    if hosts is None:
        hosts = ["192.168.18.1", "192.168.100.1"]
    res = try_login_any_host(hosts, verbose=verbose)
    if not res:
        if verbose:
            _log("Login gagal ke semua host/credential", "ERR")
            _log("Cek: 1) modem terhubung via LAN, 2) IP laptop di subnet yang sama (contoh 192.168.100.2), 3) coba akses web UI manual di browser", "WARN")
        return False
    host, user, pwd, cookie, method = res
    if verbose:
        _log(f"Login sukses {user}@{host} via {method}", "OK")
    ok, resp = upload_config_xml(host, cookie, xml_path, verbose=verbose)
    if ok and verbose:
        _log(f"Upload {xml_path} ke {host} berhasil - modem akan reboot otomatis", "OK")
    return ok
