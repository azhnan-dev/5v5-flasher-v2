# 5v5 FLASHER — versi Linux / Termux / Windows

Alat untuk **flash firmware + ganti mode upstream ONT Huawei** (mis. EG8145V5) menjadi
**EPON / GPON / XPON** — **tanpa Windows**, tanpa `TOOLS FLASHER.exe`, dan **tanpa UDP multicast**.

Cukup **Python 3.8+ (stdlib saja)**. Jalan di **PC Linux**, **Android (Termux)**, maupun **Windows**.

> Port dari toolchain Windows (`TOOLS FLASHER.exe` + `*.bat`). Seluruh workflow
> sudah **divalidasi end-to-end pada ONT nyata**, dan bisa dijalankan **otomatis
> colok-cabut** berkat perintah `batch`.

---

## Mulai cepat (2 langkah)

```bash
git clone https://github.com/azhnan-dev/5v5-flasher-v2.git
cd 5v5-flasher-v2
sh install.sh          # Linux / Termux / macOS
```

Windows: **dobel-klik `install.bat`** (atau `install.bat` dari cmd).

`install.sh` / `install.bat` akan:

1. mendeteksi sistem & manajer paket,
2. memastikan **Python 3.8+** dan **pip** ada (kalau belum ada, dipasang), sudah ada → dilewati,
3. memasang paket proyek + `pytest` (opsional — tool ini tanpa dependensi runtime),
4. menjalankan **uji cepat** supaya kamu yakin semuanya siap.

Selesai itu langsung bisa dipakai:

```bash
cd flasher

python3 flasher.py detect     # cek modem kelihatan
python3 flasher.py backup     # backup config asli (aman, tidak mengubah apa pun)
python3 flasher.py batch      # MODE STASIUN OTOMATIS: colok -> proses -> ganti
```

Windows (dari folder `flasher`):

```bat
python flasher.py detect
python flasher.py batch
```

Atau cukup **dobel-klik `flasher\flash.bat`**.

> **Firmware `2 - R022.bin` tidak disertakan** di repo ini (lihat *Keamanan & Legal*).
> Sediakan file firmware secara terpisah, lalu taruh di folder `flasher/`.
> **Config default `flasher/defaultconfig.xml` sudah disertakan** dan langsung dipakai
> sebagai config restore.

---

## Fitur

| Fitur | Perintah |
|---|---|
| Deteksi modem + tes login | `detect` |
| Backup config asli modem | `backup` |
| Upload config default (`.xml`) | `upload-xml` |
| Flash firmware (`.bin`) via web UI | `flash-web` |
| EquipMode + restore factory (`restorehwmode.sh`) | `equipmode` |
| Ganti mode upstream (EPON/GPON/XPON) | `epon`, `upport-web` |
| Alur lengkap step-by-step | `full` |
| **Stasiun otomatis: colok-cabut, ganti modem sendiri** | **`batch`** |
| Tampilan terminal keren (warna, STEP, progress, alert) | otomatis / `--plain` |
| Unit test tanpa modem (105 test) | `python -m pytest` |

- **Anti-dobel**: modem dengan Serial Number sama tidak diproses dua kali.
- **Backup otomatis per modem** ke `backup/<SERIAL>/`.
- **Log CSV** semua modem yang diproses: `backup/batch_log.csv`.
- **Adaptif antar firmware**: URL upload diambil dari `<form action>` halaman modem,
  jadi tetap jalan di firmware yang `RequestToken`-nya beda/absen.

---

## Persyaratan

- Python 3.8+ (Termux: `pkg install python`)
- **Tidak perlu** `pip install` apa pun (hanya stdlib)
- Laptop/HP satu subnet dengan modem, contoh: `192.168.18.2/24` atau `192.168.100.2/24`
- Modem terhubung via LAN (bisa pakai adaptor USB-LAN)

---

## Contoh lain

```bash
python3 flasher.py --host 192.168.18.1 detect      # target IP manual
python3 flasher.py equipmode                       # EquipMode + restorehwmode
python3 flasher.py epon --mode epon                # set EPON (via telnet)
python3 flasher.py upport-web --mode gpon          # set GPON (via web, tanpa telnet)
python3 flasher.py backup --out backup/asli.bin    # backup ke path tertentu

python3 flasher.py full --bin "2 - R022.bin"       # alur lengkap pakai config default
python3 flasher.py batch --once                    # proses 1 modem lalu berhenti
python3 flasher.py batch --limit 3                 # proses 3 modem lalu berhenti
python3 flasher.py batch --dry-run                 # uji aman (hanya login+backup)
python3 flasher.py batch --bin-r020 R020.bin --bin-r022 "2 - R022.bin"
                                                   # pilih firmware sesuai tipe modem
python3 flasher.py --plain batch                   # tampilan polos
```

`--host` adalah **flag global** → taruh **sebelum** subcommand.

---

## Install sebagai Paket & Unit Test

### Tanpa install (paling cepat)

```bash
cd flasher
python3 flasher.py detect
```

### Install sebagai paket → dapat perintah `5v5-flasher`

```bash
pip install -e .        # tanpa dependensi runtime (stdlib saja)
5v5-flasher detect
5v5-flasher batch
```

### Jalankan unit test

```bash
pip install -r requirements-dev.txt    # hanya pytest
python -m pytest                       # dari root repo
```

Hasil saat ini: **105 test lulus dalam < 1 detik**.

> Test **tidak butuh modem sama sekali** — semua I/O (HTTP, telnet, ping, port)
> diganti objek palsu, jadi bisa dijalankan di laptop tanpa kabel LAN maupun di CI.
> Termasuk **regresi bug lapangan**:
> `RequestToken` yang opsional di firmware R022, dan `_form_action` yang dulu
> salah cocok antara `cfgfileupload.cgi` dan `ptvdfcfgfileupload.cgi`.

---

## Mode Stasiun Otomatis (`batch`)

Untuk flashing massal — tinggal **colok-cabut** modem:

```
tunggu modem terpasang
  -> login -> baca Serial Number (kunci anti-dobel) + versi firmware
  -> backup config asli ke backup/<SN>/
  -> upload config default
  -> flash firmware via web  (telnet jadi aktif)
  -> equipmode (EquipMode.sh on + restorehwmode.sh)
  -> set EPON (set upport mode 2 upportid 0x102001)
  -> verifikasi mode == 2
  -> cetak "CABUT modem ini, COLOK berikutnya" + beep
  -> tunggu dicabut -> tunggu modem baru -> ULANG
```

Ctrl+C kapan saja untuk berhenti (ringkasan tetap dicetak).

### ⚠️ Penting: web UI MATI selama equip mode

Setelah `EquipMode.sh on`, modem **sengaja mematikan web UI (port 80)** —
yang hidup hanya **telnet (port 23)**. Ini normal dan memang begitu alur
`.bat` aslinya (antara `3 - EquipmodeR022.bat` dan `4 - Epon Mode.bat` tidak
ada akses web sama sekali).

Karena itu `batch` menunggu langkah equipmode/EPON lewat **telnet**
(`wait_for_telnet`), **bukan** HTTP. Web baru kembali setelah
`EquipMode.sh off` di langkah EPON.

> Kalau GUI modem tidak bisa dibuka tapi ping & telnet jalan → **itu bukan
> modem rusak**, cukup jalankan:
> ```
> python3 flasher.py --host 192.168.100.1 epon --mode epon
> ```
> (setara `4 - Epon Mode.bat`; web balik dalam hitungan detik)

### Firmware otomatis sesuai tipe modem (R020 / R022)

Modem yang masuk bisa beda generasi. `batch` membaca `SoftwareVersion` modem
**sebelum** flash, lalu memilih file firmware yang cocok:

```
python3 flasher.py batch --bin-r020 R020.bin --bin-r022 "2 - R022.bin"
```

Kalau tidak diberi, file `R020.bin` / `2 - R022.bin` di folder `flasher/`
atau root repo terdeteksi otomatis. Versi modem sebelum & sesudah flash
dicatat di `backup/batch_log.csv`.

---

## Struktur repo

```
.
├── install.sh / install.bat   # pemasang sekali jalan (Linux/Termux/Windows)
├── flasher/                   # SEMUA yang berhubungan proses flashing
│   ├── flasher.py             # CLI utama (argparse)
│   ├── steps/
│   │   ├── modem_http.py      # login web + semua endpoint HTTP modem
│   │   ├── telnet_client.py   # klien telnet (pengganti VBS SendKeys)
│   │   ├── wait_reboot.py     # ping/port polling
│   │   ├── batch.py           # mode stasiun otomatis
│   │   └── ui.py              # lapisan tampilan terminal
│   ├── legacy/                # skrip Windows & catatan alur ASLI (referensi)
│   │   ├── AIO.bat, 3 - EquipmodeR022.bat, 4 - Epon Mode.bat, step *.bat
│   │   ├── step.md, CommandTelnetUpstreamPort.txt, CaraBalikinModemKeResetGPON.txt
│   ├── defaultconfig.xml      # config restore default (dipakai `upload-xml`/`full`/`batch`)
│   ├── flash.bat              # dobel-klik untuk mode stasiun (Windows)
│   └── README.md              # DOKUMENTASI TEKNIS LENGKAP
├── tests/                     # unit test - tanpa modem, tanpa jaringan
├── pyproject.toml             # packaging + console script `5v5-flasher`
├── requirements.txt           # kosong - memang tanpa dependensi runtime
├── requirements-dev.txt       # pytest (untuk test)
└── .gitignore                 # firmware/backup TIDAK diikutkan
```

📖 **Dokumentasi teknis lengkap ada di [`flasher/README.md`](flasher/README.md)** —
tabel endpoint per-firmware, hasil uji end-to-end, temuan penting, dan troubleshooting.

---

## Keamanan & Legal

Repo ini **sengaja tidak menyertakan** file berikut:

| File | Alasan |
|---|---|
| `2 - R022.bin`, `R020.bin` | Firmware proprietary Huawei (hak cipta) |
| `TOOLS FLASHER.exe` | Tool proprietary Huawei |
| `backup/` | Backup config modem nyata — **berisi password** |

Semua itu sudah masuk `.gitignore`. Kalau butuh, bagikan lewat kanal privat
(Google Drive/WeTransfer/USB), **jangan** di-commit ke repo publik.

`flasher/defaultconfig.xml` disertakan sebagai config restore default. Pastikan
isinya memang config umum, bukan config operator yang memuat VLAN/kredensial
pribadi.

---

## Lisensi

MIT — lihat [LICENSE](LICENSE).
