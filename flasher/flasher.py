#!/usr/bin/env python3
"""
flasher.py - Port Linux/Termux dari 5v5 FLASHER tahun 2024 R022
Mengotomatisasi step.md tanpa butuh Windows .exe / .bat
Ref: step.md, 3-EquipmodeR022.bat, 4-Epon Mode.bat, CommandTelnetUpstreamPort.txt
"""
import argparse
import hashlib
import os
import sys
import time
sys.path.insert(0, os.path.dirname(__file__))
from steps.telnet_client import TelnetClient, run_sequence
from steps.modem_http import (detect_modem, try_login_any_host, upload_xml_auto,
                              login_host, download_config, upload_firmware,
                              set_upport_mode_http, get_device_info)
from steps.wait_reboot import wait_reboot, wait_for_up, wait_for_port, ping_once
from steps.batch import run_batch, pick_bin
from steps import ui

DEFAULT_HOSTS = ["192.168.18.1", "192.168.100.1"]

# ---------------------------------------------------------------------------
# Lokasi file data (config + firmware).
# File boleh ada di dalam folder `flasher/` sendiri ATAU di root repo (satu
# tingkat di atas). Nama default dicoba berurutan, jadi kode ini sama untuk
# versi umum (defaultconfig.xml) maupun versi rnet (1_1010.xml).
# ---------------------------------------------------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

XML_NAMES = ("defaultconfig.xml", "1_1010.xml", "hw_ctree.xml", "config.xml")
BIN_NAMES = ("2 - R022.bin", "R022.bin", "firmware.bin")


def find_file(names, dirs=None):
    """Cari file pertama yang ada dari daftar nama, di flasher/ lalu root repo."""
    dirs = dirs or (BASE, ROOT)
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return os.path.join(BASE, names[0])  # belum ada -> path default (buat pesan error)


def log(msg, level="INFO"):
    ui.log(msg, level)

def cmd_detect(args):
    hosts = [args.host] if args.host != "auto" else DEFAULT_HOSTS
    found = detect_modem(hosts, verbose=True)
    if found:
        log(f"Ditemukan: {', '.join(found)}", "OK")
        for h in found:
            alive = ping_once(h)
            log(f"  {h} ping={'ok' if alive else 'fail'}")
            res = try_login_any_host([h], verbose=False)
            if res:
                _, user, _, _, method = res
                log(f"  {h} login bisa dengan {user} ({method})", "OK")
            else:
                log(f"  {h} login belum dites / gagal", "WARN")
        return 0
    else:
        log("Tidak ada modem terdeteksi. Cek kabel LAN & IP laptop (harus 192.168.100.2 atau 192.168.18.2 /24).", "ERR")
        return 1

def cmd_upload_xml(args):
    xml = args.xml
    if not os.path.isfile(xml):
        log(f"File tidak ada: {xml}", "ERR")
        return 1
    hosts = [args.host] if args.host != "auto" else DEFAULT_HOSTS
    ok = upload_xml_auto(xml, hosts=hosts, verbose=True)
    if ok:
        log("Upload selesai, modem akan reboot. Lanjut: python3 flasher.py wait-reboot", "OK")
        return 0
    else:
        log("Upload gagal. Coba upload manual via browser dulu.", "ERR")
        return 1

def cmd_wait_reboot(args):
    host = args.host
    if host == "auto":
        found = detect_modem(DEFAULT_HOSTS, verbose=False)
        host = found[0] if found else "192.168.100.1"
        log(f"Auto host -> {host}")
    ok = wait_reboot(host, verbose=True)
    return 0 if ok else 1

def _resolve_host(host, verbose=False):
    if host == "auto":
        found = detect_modem(DEFAULT_HOSTS, verbose=False)
        host = found[0] if found else "192.168.100.1"
        if verbose:
            log(f"Auto host -> {host}")
    return host


def cmd_backup(args):
    host = _resolve_host(args.host, verbose=True)
    ok, cookie = login_host(host, verbose=True)
    if not ok:
        log(f"Login gagal ke {host}", "ERR")
        return 1
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = args.out or os.path.join(ROOT, "backup", f"config_{host}_{ts}.bin")
    okb, info = download_config(host, cookie, out, verbose=True)
    if okb:
        log(f"Backup tersimpan: {info}", "OK")
        return 0
    log(f"Backup gagal: {info}", "ERR")
    return 1


def cmd_flash_web(args):
    host = _resolve_host(args.host, verbose=True)
    if not os.path.isfile(args.bin):
        log(f"File tidak ada: {args.bin}", "ERR")
        return 1
    ok, cookie = login_host(host, verbose=True)
    if not ok:
        log(f"Login gagal ke {host}", "ERR")
        return 1
    log("PERHATIAN: upload firmware via web UI (Firmwareupload.cgi). Pastikan file benar.", "WARN")
    okf, text = upload_firmware(host, cookie, args.bin, verbose=True)
    if okf:
        log("Upload firmware diterima modem. Tunggu reboot 1-2 menit.", "OK")
        if not args.no_wait:
            wait_for_up(host, timeout=120, verbose=True)
        return 0
    log("Upload firmware ditolak/gagal. Cek respons di atas.", "ERR")
    return 1


def cmd_upport_web(args):
    host = _resolve_host(args.host, verbose=True)
    ok, cookie = login_host(host, verbose=True)
    if not ok:
        log(f"Login gagal ke {host}", "ERR")
        return 1
    mode_map = {"gpon": 1, "epon": 2, "xpon": 4, "lan": 3, "wifi": 8}
    mode = mode_map.get(args.mode, 2)
    oku, text = set_upport_mode_http(host, cookie, mode, reboot=True, verbose=True)
    if oku:
        log(f"Upport mode {args.mode} ({mode}) dikirim. Modem reboot...", "OK")
        if not args.no_wait:
            wait_for_up(host, timeout=120, verbose=True)
        return 0
    log("Set upport via web gagal. Cek respons di atas.", "ERR")
    return 1


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).digest()


def _build_bin_map(args, dirs):
    """
    Peta firmware per keluarga versi modem: {"R020": path, "R022": path}.

    Sumber: --bin-r020 / --bin-r022. Kalau tidak diberi, dicari otomatis
    dengan nama file umum di folder `flasher/` atau root repo.
    Modem R020 -> R020, R022 -> R022.
    """
    bin_map = {}
    kandidat = (("R020", getattr(args, "bin_r020", None), ("2 - R020.bin", "R020.bin")),
                ("R022", getattr(args, "bin_r022", None), ("2 - R022.bin", "R022.bin")))
    for fam, arg, names in kandidat:
        p = arg
        if not p:
            for d in dirs:
                for n in names:
                    cand = os.path.join(d, n)
                    if os.path.isfile(cand):
                        p = cand
                        break
                if p:
                    break
        if p:
            p = os.path.abspath(p)
            if os.path.isfile(p):
                bin_map[fam] = p
                if not arg:
                    log(f"Firmware {fam} terdeteksi otomatis: {os.path.basename(p)}")
            else:
                log(f"File firmware {fam} tidak ada: {p}", "WARN")

    # Safety net: 2 file firmware identik biasanya karena salah copy/rename.
    fams = sorted(bin_map)
    for i in range(len(fams)):
        for j in range(i + 1, len(fams)):
            a, b = bin_map[fams[i]], bin_map[fams[j]]
            try:
                if os.path.getsize(a) != os.path.getsize(b):
                    continue
                if _sha256(a) != _sha256(b):
                    continue
            except Exception:
                continue
            log(f"info: firmware {fams[i]} dan {fams[j]} isinya SAMA (satu paket, dua nama) - "
                f"aman, paket ini tetap dipakai untuk semua modem.", "INFO")
    return bin_map


def cmd_batch(args):
    xml = os.path.abspath(args.xml) if args.xml else find_file(XML_NAMES)
    binp = os.path.abspath(args.bin) if args.bin else find_file(BIN_NAMES)
    backup_root = os.path.join(ROOT, "backup")
    hosts = None if args.host == "auto" else [args.host]
    bin_map = _build_bin_map(args, (BASE, ROOT))

    if not args.dry_run:
        if not args.xml and not os.path.isfile(xml):
            log(f"File config tidak ada: {xml}", "ERR")
            return 1
        if not args.bin and not os.path.isfile(binp):
            log(f"File firmware tidak ada: {binp}", "ERR")
            return 1
        log("PERHATIAN: mode batch MENGUBAH modem (config + flash + equipmode + EPON).", "WARN")
    return run_batch(xml, binp, backup_root=backup_root, limit=args.limit,
                     once=args.once, dry_run=args.dry_run, hosts=hosts,
                     bin_map=bin_map or None)


def _run_telnet_sequence(host, user, password, commands, verbose=True):
    return run_sequence(host, user, password, commands, verbose=verbose)

def cmd_reboot(args):
    host = _resolve_host(args.host, verbose=True)
    log(f"=== Reboot {host} via telnet ===")
    ok = False
    res = ""
    for seq in (["reboot"], ["su", "reboot"], ["su", "shell", "reboot"]):
        log(f"Coba: {' ; '.join(seq)}")
        ok, res = _run_telnet_sequence(host, "root", "admin", seq)
        if ok:
            break
    if ok:
        log("Perintah reboot dikirim.", "OK")
        if not args.no_wait:
            time.sleep(5)
            wait_for_up(host, timeout=120, verbose=True)
            wait_for_port(host, 23, timeout=120, verbose=True)
        return 0
    log(f"Reboot gagal: {res}", "ERR")
    return 1


def cmd_equipmode(args):
    host = args.host
    if host == "auto":
        found = detect_modem(DEFAULT_HOSTS, verbose=False)
        host = found[0] if found else "192.168.100.1"
    log(f"=== EquipMode di {host} ===")
    log("Tahap 1: EquipMode.sh on")
    ok1, res1 = _run_telnet_sequence(host, "root", "admin", ["su","shell","EquipMode.sh on","exit","quit","quit"])
    if not ok1:
        log(f"Tahap 1 gagal: {res1}", "WARN")
    time.sleep(2)
    log("Tahap 2: restorehwmode.sh + reset")
    ok2, res2 = _run_telnet_sequence(host, "root", "admin", ["su","shell","sudo restorehwmode.sh","exit","reset"])
    if ok2:
        log("EquipMode selesai, modem akan reset/reboot. Tunggu 60-90 detik lalu lanjut epon.", "OK")
    else:
        log(f"Tahap 2 hasil: {res2}", "WARN")
    if not args.no_wait:
        log("Menunggu modem hidup kembali...")
        wait_for_up(host, timeout=90, verbose=True)
        wait_for_port(host, 23, timeout=60, verbose=True)
    return 0 if (ok1 and ok2) else 1

def cmd_epon(args):
    host = args.host
    if host == "auto":
        found = detect_modem(DEFAULT_HOSTS, verbose=False)
        host = found[0] if found else "192.168.100.1"
    mode = args.mode
    mode_map = {"gpon": "1","epon": "2","xpon": "4","lan1": "3","lan2": "3","lan3": "3","lan4": "3"}
    upport_map = {"gpon": "0x102001","epon": "0x102001","xpon": "0x102001","lan1": "0x00000001","lan2": "0x00000002","lan3": "0x00000003","lan4": "0x00000004"}
    mode_val = mode_map.get(mode, "2")
    upport_val = upport_map.get(mode, "0x102001")
    log(f"=== Set Upport Mode {mode.upper()} ({mode_val} {upport_val}) di {host} ===")
    ok, res = _run_telnet_sequence(host, "root", "admin", ["su", f"set upport mode {mode_val} upportid {upport_val}", "shell","EquipMode.sh off","reboot","exit","reset"])
    if ok:
        log(f"Mode {mode} berhasil, modem reboot...", "OK")
    else:
        log(f"Hasil: {res}", "WARN")
    if not args.no_wait:
        wait_for_up(host, timeout=90, verbose=True)
        wait_for_port(host, 23, timeout=60, verbose=True)
    return 0 if ok else 1

def cmd_aio(args):
    host = args.host
    if host == "auto":
        found = detect_modem(DEFAULT_HOSTS, verbose=False)
        host = found[0] if found else "192.168.100.1"
    log(f"=== AIO di {host} ===")
    rc1 = cmd_equipmode(argparse.Namespace(host=host, no_wait=False))
    if rc1 != 0:
        log("AIO: equipmode ada warning, tetap lanjut ke epon...", "WARN")
    time.sleep(5)
    wait_for_up(host, timeout=90, verbose=True)
    rc2 = cmd_epon(argparse.Namespace(host=host, mode="epon", no_wait=False))
    if rc1 == 0 and rc2 == 0:
        log("AIO selesai - modem dalam mode EPON, siap setting VLAN/Internet.", "OK")
        return 0
    else:
        log("AIO selesai dengan warning, cek log di atas.", "WARN")
        return 1

def cmd_full(args):
    xml = args.xml
    if not xml:
        found = find_file(XML_NAMES)
        if os.path.isfile(found):
            xml = found
            log(f"Config default dipakai: {xml}")
    host = args.host
    if host == "auto":
        found = detect_modem(DEFAULT_HOSTS, verbose=True)
        host = found[0] if found else "192.168.100.1"
        log(f"Auto host -> {host}")
    if xml:
        log(f"Langkah 1: upload {xml} ke {host}")
        hosts = [host]
        ok = upload_xml_auto(xml, hosts=hosts, verbose=True)
        if not ok:
            log("Upload XML gagal, hentikan.", "ERR")
            return 1
        log("Menunggu reboot setelah upload XML...")
        wait_reboot(host)
    else:
        log("Skip upload XML (tidak ada --xml), langsung lanjut.", "WARN")
    bin_map = _build_bin_map(args, (BASE, ROOT))
    bin_use = args.bin
    if not bin_use and bin_map:
        bin_use = bin_map.get("R022")
        if not bin_use:
            cand = find_file(BIN_NAMES)
            bin_use = cand if os.path.isfile(cand) else None
    if bin_use:
        ok, cookie = login_host(host, verbose=True)
        if not ok:
            log("Login web gagal, hentikan.", "ERR")
            return 1
        if bin_map:
            sw = (get_device_info(host, cookie) or {}).get("SoftwareVersion", "")
            chosen, why = pick_bin(sw, bin_use, bin_map)
            if chosen:
                if chosen != bin_use:
                    log(f"Firmware dipilih otomatis: {os.path.basename(str(chosen))} ({why})")
                bin_use = chosen
        log(f"Langkah 2: upload firmware {bin_use} via web UI (Firmwareupload.cgi)")
        okf, text = upload_firmware(host, cookie, bin_use, verbose=True)
        if not okf:
            log("Upload firmware via web ditolak. Hentikan (atau pakai flash UDP multicast manual).", "ERR")
            return 1
        log("Firmware diterima modem. Tunggu modem siap (telnet aktif)...", "OK")
        wait_for_up(host, timeout=120, verbose=True)
        wait_for_port(host, 23, timeout=120, verbose=True)
    else:
        log("Langkah 2: skip flash bin (tidak ada --bin). Jika sudah flash via Windows, lanjut.", "WARN")
    log("Langkah 3: EquipMode")
    cmd_equipmode(argparse.Namespace(host=host, no_wait=False))
    log("Menunggu sebelum Epon...")
    wait_for_up(host, timeout=90, verbose=True)
    log("Langkah 4: Epon Mode")
    cmd_epon(argparse.Namespace(host=host, mode="epon", no_wait=False))
    log("FULL selesai.", "OK")
    return 0

def build_parser():
    p = argparse.ArgumentParser(description="5v5 FLASHER port Linux/Termux - flash firmware + ganti mode upstream ONT Huawei, tanpa Windows")
    p.add_argument("--host", default="auto", help="IP modem (default: auto detect 192.168.18.1 / 192.168.100.1)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("detect", help="Deteksi modem di jaringan")
    s.set_defaults(func=cmd_detect)
    s = sub.add_parser("upload-xml", help="Upload file config XML ke modem (menggantikan upload manual)")
    s.add_argument("xml", help="path ke file .xml (default: cari otomatis di folder flasher/)")
    s.set_defaults(func=cmd_upload_xml)
    s = sub.add_parser("wait-reboot", help="Tunggu modem reboot sampai siap")
    s.set_defaults(func=cmd_wait_reboot)
    s = sub.add_parser("equipmode", help="Jalankan EquipMode.sh on + restorehwmode.sh (butuh telnet)")
    s.add_argument("--no-wait", action="store_true", help="jangan tunggu reboot setelahnya")
    s.set_defaults(func=cmd_equipmode)
    s = sub.add_parser("epon", help="Set mode EPON/GPON/XPON via telnet")
    s.add_argument("--mode", default="epon", choices=["gpon","epon","xpon","lan1","lan2","lan3","lan4"], help="mode upport (default: epon)")
    s.add_argument("--no-wait", action="store_true")
    s.set_defaults(func=cmd_epon)
    s = sub.add_parser("aio", help="Gabungan equipmode + epon (seperti AIO.bat)")
    s.set_defaults(func=cmd_aio)
    s = sub.add_parser("full", help="Alur lengkap step.md (upload-xml -> flash-web -> equipmode -> epon)")
    s.add_argument("--xml", default=None, help="path ke .xml untuk upload (default: cari otomatis di folder flasher/)")
    s.add_argument("--bin", default=None, help="path ke .bin untuk di-flash via web UI")
    s.add_argument("--bin-r020", default=None, help="firmware untuk modem keluarga R019/R020 (opsional)")
    s.add_argument("--bin-r022", default=None, help="firmware untuk modem keluarga R022 (opsional)")
    s.set_defaults(func=cmd_full)
    s = sub.add_parser("backup", help="Download/backup config modem (cfgfiledown.cgi) - aman")
    s.add_argument("--out", default=None, help="path file output (default backup/config_<host>_<ts>.bin)")
    s.set_defaults(func=cmd_backup)
    s = sub.add_parser("flash-web", help="Upload firmware .bin via web UI (Fase 2 - terbukti bekerja)")
    s.add_argument("bin", help="path ke file .bin (default: cari otomatis di folder flasher/)")
    s.add_argument("--no-wait", action="store_true")
    s.set_defaults(func=cmd_flash_web)
    s = sub.add_parser("reboot", help="Reboot modem via telnet")
    s.add_argument("--no-wait", action="store_true")
    s.set_defaults(func=cmd_reboot)
    s = sub.add_parser("batch", help="MODE STATION OTOMATIS: proses modem satu per satu, ganti modem otomatis")
    s.add_argument("--xml", default=None, help="config default (default: cari otomatis: defaultconfig.xml / 1_1010.xml)")
    s.add_argument("--bin", default=None, help="firmware default/fallback (default: cari otomatis: 2 - R022.bin)")
    s.add_argument("--bin-r020", default=None, help="firmware untuk modem keluarga R019/R020 (opsional)")
    s.add_argument("--bin-r022", default=None, help="firmware untuk modem keluarga R022 (opsional)")
    s.add_argument("--limit", type=int, default=0, help="stop setelah N modem (0 = tanpa batas)")
    s.add_argument("--once", action="store_true", help="proses 1 modem lalu berhenti")
    s.add_argument("--dry-run", action="store_true", help="hanya login+backup, tidak mengubah modem")
    s.set_defaults(func=cmd_batch)
    s = sub.add_parser("upport-web", help="Set upstream port mode via web UI (setara 'set upport mode')")
    s.add_argument("--mode", default="epon", choices=["gpon", "epon", "xpon", "lan", "wifi"], help="mode upport (default: epon)")
    s.add_argument("--no-wait", action="store_true")
    s.set_defaults(func=cmd_upport_web)
    s = sub.add_parser("flash", help="(Fase 2 STUB) Flash .bin via UDP multicast - belum implementasi")
    s.add_argument("bin", help="path ke file .bin (default: cari otomatis di folder flasher/)")
    s.set_defaults(func=lambda a: (log("flash UDP multicast belum implementasi (butuh pcap Fase 2)", "ERR"), 1)[1])
    return p

def main():
    # --plain boleh ditaruh di mana saja (tanpa warna/banner)
    argv = [a for a in sys.argv[1:] if a != "--plain"]
    plain = len(argv) != (len(sys.argv) - 1)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "host"):
        # cari global --host jika dipanggil sebagai `flasher.py --host X cmd`
        args.host = "auto"
        if "--host" in argv:
            idx = argv.index("--host")
            if idx+1 < len(argv):
                val = argv[idx+1]
                if val not in ["detect","upload-xml","wait-reboot","equipmode","epon","aio","full","flash","backup","flash-web","upport-web","reboot","batch"]:
                    args.host = val
    if plain:
        ui.set_plain(True)
    if args.cmd != "batch":
        # batch menampilkan bannernya sendiri di steps/batch.py
        ui.setup_console()
        ui.banner("PORT LINUX / TERMUX  ·  TANPA WINDOWS")
    rc = args.func(args)
    sys.exit(rc)

if __name__ == "__main__":
    main()
