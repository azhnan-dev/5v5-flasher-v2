"""
batch.py - Mode STATION OTOMATIS.

Alur per modem (mengikuti step.md, sepenuhnya via HTTP + telnet):
  tunggu modem terpasang
    -> login
    -> baca identitas (Serial Number)  <- kunci anti-dobel
    -> backup config awal
    -> upload config default (1_1010.xml)
    -> flash firmware via web (2 - R022.bin)  [telnet jadi aktif]
    -> equipmode (EquipMode.sh on + restorehwmode.sh)
    -> set mode EPON (set upport mode 2 upportid 0x102001)
    -> verifikasi
  -> "SILAKAN CABUT MODEM INI, COLOK MODEM BERIKUTNYA"
  -> tunggu modem dicabut -> tunggu modem baru -> ulang

Tanpa dependensi eksternal (stdlib).
"""
import os
import re
import csv
import time
import datetime

from steps.modem_http import (detect_modem, login_host, get_device_info, short_serial,
                              download_config, upload_xml_auto, upload_firmware,
                              get_upport_mode)
from steps.wait_reboot import wait_for_up, wait_for_port, port_open
from steps.telnet_client import run_sequence
from steps import ui

DEFAULT_HOSTS = ["192.168.18.1", "192.168.100.1"]

# urutan perintah telnet (persis seperti .bat asli)
SEQ_EQUIPMODE_1 = ["su", "shell", "EquipMode.sh on", "exit", "quit", "quit"]
SEQ_EQUIPMODE_2 = ["su", "shell", "sudo restorehwmode.sh", "exit", "reset"]
SEQ_EPON_EPON = ["su", "set upport mode 2 upportid 0x102001",
                 "shell", "EquipMode.sh off", "reboot", "exit", "reset"]
SEQ_REBOOT = ["reboot"]


def log(msg, level="INFO"):
    """Log dengan tampilan dari steps/ui.py (warna, ikon, timestamp)."""
    ui.log(msg, level)


def wait_for_modem(hosts=None, poll=3, timeout=None, quiet=False):
    """
    Tunggu sampai ada modem yang WEB UI-nya hidup (port 80/HTTP). Return host.

    timeout=None -> tunggu tanpa batas (perilaku lama).
    timeout=<detik> -> return None kalau sampai timeout tidak ada.

    CATATAN: web UI MATI saat modem dalam equip mode (sesudah `EquipMode.sh on`).
    Untuk fase itu pakai `wait_for_telnet()`, jangan fungsi ini.
    """
    hosts = hosts or DEFAULT_HOSTS
    deadline = None if timeout is None else time.time() + timeout
    while True:
        found = detect_modem(hosts, verbose=False)
        if found:
            return found[0]
        if deadline is not None and time.time() >= deadline:
            if not quiet:
                log(f"Tidak ada modem dengan web UI hidup setelah {timeout}s "
                    f"(dicoba: {', '.join(hosts)})", "WARN")
            return None
        time.sleep(poll)


def wait_for_telnet(hosts=None, timeout=300, poll=3, quiet=False):
    """
    Tunggu sampai ada modem yang TELNET-nya (port 23) terbuka. Return host / None.

    Ini pengganti `wait_for_modem()` sesudah equipmode: pada fase itu
    `EquipMode.sh on` sengaja mematikan web UI, jadi menunggu port 80
    = menunggu selamanya (penyebab batch stuck di step 6).
    """
    hosts = hosts or DEFAULT_HOSTS
    deadline = time.time() + timeout
    while True:
        for h in hosts:
            if port_open(h, 23, timeout=2):
                if not quiet:
                    log(f"Telnet {h}:23 terbuka", "OK")
                return h
        if time.time() >= deadline:
            if not quiet:
                log(f"Telnet (port 23) tidak terbuka setelah {timeout}s "
                    f"(dicoba: {', '.join(hosts)})", "WARN")
            return None
        time.sleep(poll)


_FW_FAMILY_RE = re.compile(r"R(\d{3})", re.IGNORECASE)


def fw_family(version):
    """
    Ambil keluarga firmware dari string versi.
      'V5R020C10S195'        -> 'R020'
      'V500R022C10SPC167'    -> 'R022'
      'V300R020C10SPC212'    -> 'R020'
      '' / tidak dikenal     -> ''
    """
    m = _FW_FAMILY_RE.search(version or "")
    return ("R" + m.group(1)).upper() if m else ""


def pick_bin(version, bin_default=None, bin_map=None):
    """
    Pilih file firmware yang cocok dengan versi modem.

    bin_map contoh: {"R020": "R020.bin", "R022": "2 - R022.bin"}
    Return (path, keterangan).
    """
    fam = fw_family(version)
    if bin_map:
        if fam and bin_map.get(fam):
            return bin_map[fam], f"cocok {fam} (versi modem {version})"
        if fam:
            return bin_default, f"tidak ada file untuk {fam}, pakai default"
    return bin_default, "default"


def wait_for_removal(hosts=None, stable=8, poll=2, quiet=False):
    """Tunggu sampai modem benar-benar DICABUT (semua host mati selama `stable` detik)."""
    hosts = hosts or DEFAULT_HOSTS
    down_since = None
    while True:
        found = detect_modem(hosts, verbose=False)
        if not found:
            if down_since is None:
                down_since = time.time()
                if not quiet:
                    log("Modem tidak merespon, konfirmasi cabut...")
            elif time.time() - down_since >= stable:
                return True
        else:
            if down_since is not None and not quiet:
                log("Modem muncul lagi, masih menunggu dicabut...")
            down_since = None
        time.sleep(poll)


def login_wait(host, timeout=180, poll=5, quiet=False):
    """Coba login berulang sampai berhasil (modem kadang belum siap setelah reboot)."""
    t0 = time.time()
    while True:
        ok, cookie = login_host(host, verbose=False)
        if ok:
            return True, cookie
        if time.time() - t0 >= timeout:
            return False, ""
        if not quiet:
            log(f"Login belum siap di {host}, tunggu {poll}s...")
        time.sleep(poll)


def _csv_append(backup_root, row):
    """
    Tulis 1 baris ke backup/batch_log.csv.

    Kalau ada kolom baru (mis. software_after_flash) yang belum ada di file lama,
    header lama otomatis dimigrasi supaya history tetap utuh & terbaca.
    """
    if not backup_root:
        return
    try:
        os.makedirs(backup_root, exist_ok=True)
        path = os.path.join(backup_root, "batch_log.csv")
        old_rows = []
        old_cols = []
        if os.path.isfile(path):
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                old_cols = list(reader.fieldnames or [])
                old_rows = list(reader)

        cols = old_cols + [c for c in row.keys() if c not in old_cols]
        if old_cols and old_rows and cols == old_cols:
            # skema sama -> cukup append
            with open(path, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=cols).writerow(row)
        else:
            # file baru / header berubah -> tulis ulang (header + baris lama + baris baru)
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                for r in old_rows:
                    w.writerow({k: (v if v is not None else "") for k, v in r.items()})
                w.writerow(row)
    except Exception as e:
        log(f"Gagal tulis log CSV: {e}", "WARN")


def process_one(host, xml, bin_path, backup_root=None, dry_run=False, quiet=False,
                bin_map=None):
    """Proses 1 modem. Return dict hasil."""
    res = {"time": datetime.datetime.now().isoformat(timespec="seconds"),
           "host": host, "serial": "", "serial_short": "", "model": "",
           "software": "", "mac": "", "upport_mode": "", "status": "started", "note": "",
           "software_after_flash": "", "software_final": "", "flash_resp": ""}

    # --- 1) login ---
    ui.step(1)
    with ui.Spinner(f"Login ke {host}"):
        ok, cookie = login_wait(host, timeout=180, quiet=True)
    if not ok:
        res["status"], res["note"] = "failed", "login gagal"
        return res
    log(f"Login berhasil di {host}", "OK")

    # --- 2) identitas ---
    ui.step(2)
    info = get_device_info(host, cookie) or {}
    sn = info.get("SerialNumber", "")
    res.update({"serial": sn, "serial_short": short_serial(sn),
                "model": info.get("ModelName", "?"),
                "software": info.get("SoftwareVersion", "?"),
                "mac": info.get("Mac", "?")})
    log(f"Modem {res['model']} | SN={res['serial_short']} | SW={res['software']} | MAC={res['mac']}", "OK")

    # --- 3) backup config awal ---
    ui.step(3)
    if backup_root:
        d = os.path.join(backup_root, res["serial_short"] or "unknown")
        os.makedirs(d, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = os.path.join(d, f"hw_ctree_awal_{ts}.bin")
        with ui.Spinner("Backup config asli"):
            okb, infob = download_config(host, cookie, out, verbose=False)
        log(f"Backup config awal: {infob}" if okb else f"Backup awal GAGAL: {infob}",
            "OK" if okb else "WARN")

    if dry_run:
        res["status"], res["note"] = "dry-run", "hanya login+backup (dry-run)"
        return res

    # --- 4) upload config default ---
    ui.step(4)
    if xml:
        with ui.Spinner(f"Upload config {os.path.basename(xml)}"):
            okx = upload_xml_auto(xml, hosts=[host], verbose=False)
        if not okx:
            res["status"], res["note"] = "failed", "upload config gagal"
            return res
        log("Config terupload, modem reboot ...", "OK")
        time.sleep(10)
        with ui.Spinner("Menunggu modem hidup kembali"):
            host2 = wait_for_modem(timeout=240, quiet=True)
        if not host2:
            res["status"], res["note"] = "failed", "modem tidak kembali setelah upload config (timeout 240s)"
            return res
        host = host2
        log(f"Modem hidup lagi di {host}", "OK")
        with ui.Spinner("Login ulang"):
            ok, cookie = login_wait(host, timeout=180, quiet=True)
        if not ok:
            res["status"], res["note"] = "failed", "login pasca config gagal"
            return res

    # --- 5) flash firmware via web ---
    ui.step(5)
    bin_use, why = bin_path, "default"
    if bin_path and bin_map:
        bin_use, why = pick_bin(res["software"], bin_path, bin_map)
    if bin_use:
        log(f"Firmware dipakai: {os.path.basename(str(bin_use))}  ({why})")
        with ui.Spinner(f"Upload firmware {os.path.basename(str(bin_use))}"):
            okf, resp = upload_firmware(host, cookie, bin_use, verbose=False)
        res["flash_resp"] = " ".join(str(resp).split())[:120]
        if not okf:
            res["status"], res["note"] = "failed", "firmware ditolak web"
            return res
        log("Firmware diterima web. Menunggu telnet aktif ...", "OK")
        time.sleep(5)
        with ui.Spinner("Menunggu telnet aktif (port 23)"):
            wait_for_up(host, timeout=180, verbose=False)
            host2 = wait_for_telnet(hosts=[host], timeout=180, quiet=True)
        if not host2:
            res["status"], res["note"] = "failed", "telnet tidak terbuka setelah flash"
            return res
        host = host2
        log("Telnet aktif (port 23 terbuka)", "OK")

        # Cek apakah flash BENAR-BENAR mengubah versi firmware.
        # (web kadang belum hidup di titik ini -> cek dilewati, bukan gagal)
        if wait_for_port(host, 80, timeout=75, verbose=False):
            okv, ckv = login_wait(host, timeout=60, quiet=True)
            if okv:
                res["software_after_flash"] = (get_device_info(host, ckv) or {}).get(
                    "SoftwareVersion", "")
                if res["software_after_flash"]:
                    log(f"Versi setelah flash: {res['software_after_flash']}", "OK")

    # --- 6) equipmode ---
    ui.step(6)
    with ui.Spinner("EquipMode.sh on"):
        ok1, _ = run_sequence(host, "root", "admin", SEQ_EQUIPMODE_1, verbose=False)
    time.sleep(2)
    with ui.Spinner("restorehwmode.sh (mode default pabrik)"):
        ok2, _ = run_sequence(host, "root", "admin", SEQ_EQUIPMODE_2, verbose=False)
    if not (ok1 or ok2):
        res["status"], res["note"] = "failed", "equipmode gagal"
        return res
    log("EquipMode selesai. Modem reboot ...", "OK")
    time.sleep(10)
    # PENTING: selama equip mode, WEB UI MATI (cuma telnet yang hidup).
    # Menunggu port 80 di sini = menunggu selamanya (bug lama: batch stuck di step 6).
    with ui.Spinner("Menunggu modem kembali (via telnet)"):
        host2 = wait_for_telnet(hosts=[host], timeout=300, quiet=True)
    if not host2:
        res["status"], res["note"] = "failed", "modem tidak kembali setelah equipmode (telnet timeout 300s)"
        return res
    host = host2
    log(f"Modem kembali di {host} (via telnet)", "OK")

    # --- 7) set EPON ---
    ui.step(7)
    with ui.Spinner("set upport mode 2 (EPON)"):
        oke, _ = run_sequence(host, "root", "admin", SEQ_EPON_EPON, verbose=False)
    if not oke:
        res["status"], res["note"] = "failed", "set upport mode gagal"
        return res
    log("Perintah EPON dikirim. Modem reboot ...", "OK")
    time.sleep(10)
    with ui.Spinner("Menunggu modem kembali (via telnet)"):
        host2 = wait_for_telnet(hosts=[host], timeout=300, quiet=True)
    if not host2:
        res["status"], res["note"] = "failed", "modem tidak kembali setelah set EPON (telnet timeout 300s)"
        return res
    host = host2

    # --- 8) verifikasi ---
    ui.step(8)
    ok = False
    cookie = ""
    with ui.Spinner("Verifikasi (menunggu web UI hidup)"):
        host2 = wait_for_modem(hosts=[host], timeout=240, quiet=True)
        if host2:
            host = host2
            ok, cookie = login_wait(host, timeout=120, quiet=True)
    if ok:
        info2 = get_device_info(host, cookie) or {}
        res["software_final"] = info2.get("SoftwareVersion", "")
        mode = get_upport_mode(host, cookie)
        res["upport_mode"] = mode or "?"
        if mode == "2":
            res["status"], res["note"] = "ok", "EPON aktif (mode=2)"
        else:
            res["status"], res["note"] = "warning", f"upport mode={mode} (bukan 2)"
        if bin_use and res["software"] and res["software_final"] \
                and res["software"] == res["software_final"]:
            res["note"] += " | PERHATIAN: versi firmware tidak berubah"
            log(f"Versi firmware TIDAK berubah (tetap {res['software_final']}) - "
                f"flash sepertinya tidak berefek.", "WARN")
    else:
        res["status"], res["note"] = "warning", "verifikasi gagal (web tidak hidup)"
    res["host"] = host
    return res


def run_batch(xml, bin_path, backup_root=None, limit=0, once=False,
              dry_run=False, hosts=None, quiet=False, bin_map=None):
    """Loop station otomatis."""
    hosts = hosts or DEFAULT_HOSTS
    done = {}
    n = 0

    ui.setup_console()
    ui.banner("STATION MODE  ·  OTOMATIS COLOK-CABUT")
    ui.kv("config", xml)
    ui.kv("firmware", bin_path)
    if bin_map:
        for fam, path in sorted(bin_map.items()):
            ui.kv(f"  - {fam}", path or "(tidak diset)")
    ui.kv("hosts", ", ".join(hosts))
    ui.kv("anti-dobel", "Ya - berdasarkan Serial Number")
    if dry_run:
        ui.alert(["MODE UJI AMAN (dry-run) aktif.",
                  "Hanya login + backup. Modem TIDAK diubah."],
                 title="DRY-RUN", color="yellow", icon="!")
    ui.rule("menunggu modem")

    while True:
        with ui.Spinner("Menunggu modem terpasang"):
            host = wait_for_modem(hosts)
        ui.rule("modem terdeteksi")
        log(f"Modem terdeteksi di {host}", "OK")

        # identifikasi dulu supaya tidak proses modem yang sama 2x
        with ui.Spinner("Membaca identitas modem"):
            ok, cookie = login_wait(host, timeout=120, quiet=True)
        sn = ""
        info = {}
        if ok:
            info = get_device_info(host, cookie) or {}
            sn = info.get("SerialNumber", "")
        if sn and sn in done:
            log(f"Modem {short_serial(sn)} SUDAH pernah diproses. Cabut & colok modem berikutnya.", "WARN")
            wait_for_removal(hosts)
            continue

        n += 1
        ui.alert([f"MODEM #{n}   {ui.sym('dot')}   SN {short_serial(sn) or '?'}",
                  f"{info.get('ModelName', '?')}  {ui.sym('dot')}  host {host}"],
                 title="MULAI PROSES", color="cyan", icon=ui.sym("raquo"))

        res = process_one(host, xml, bin_path, backup_root=backup_root,
                          dry_run=dry_run, quiet=quiet, bin_map=bin_map)
        res["index"] = n
        if res.get("serial"):
            done[res["serial"]] = res
        _csv_append(backup_root, res)

        if res["status"] == "ok":
            ui.success_big(res.get("serial_short") or "?", res.get("model", ""),
                           f"upport mode={res.get('upport_mode', '?')}")
        elif res["status"] == "dry-run":
            ui.alert([f"MODEM #{n}   {ui.sym('dot')}   SN {res.get('serial_short') or '?'}",
                      "Tidak ada perubahan pada modem.",
                      "",
                      f"{ui.sym('raquo') * 3}  CABUT modem ini untuk lanjut  {ui.sym('raquo') * 3}"],
                     title="UJI AMAN SELESAI", color="cyan", icon=ui.sym("raquo"))
        else:
            ui.fail_big(res.get("serial_short") or "?",
                        f"{res['status'].upper()} - {res['note']}")

        if once or (limit and n >= limit):
            log(f"Selesai {n} modem. Berhenti.")
            break

        with ui.Spinner("Menunggu modem dicabut"):
            wait_for_removal(hosts)
        ui.rule("siap untuk modem berikutnya")
        log("Modem sudah dicabut. Menunggu modem berikutnya ...", "OK")

    # ringkasan
    ui.rule("ringkasan")
    log(f"Total {n} modem diproses", "OK")
    rows = [("#" + str(r.get("index", "?")), r.get("serial_short", "?"),
             r.get("model", "?"), r["status"], r["note"]) for r in done.values()]
    if rows:
        ui.table(rows, headers=("#", "SERIAL", "MODEL", "STATUS", "KETERANGAN"))
    else:
        log("Tidak ada modem yang diproses.", "WARN")
    ui.rule()
    return 0
