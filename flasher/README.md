# 5v5 FLASHER — Port Linux / Termux (Fase 1 + Fase 2 SELESAI)

Port dari `5v5 - tahun 2024 R022` (Windows .exe/.bat) ke Python stdlib, jalan di **Linux PC** dan **Android Termux** tanpa butuh Windows.

**Status: seluruh workflow `step.md` sudah tervalidasi di ONT nyata (Huawei EG8145V5) tanpa Windows / tanpa UDP multicast.**

> **Isi folder ini:** `flasher.py` + `steps/` (kode), `defaultconfig.xml` (config restore
> yang dipakai `upload-xml`/`full`/`batch`), `legacy/` (skrip Windows & catatan alur asli
> sebagai referensi), dan `BATCH - Station Mode.bat` (dobel-klik di Windows).
> Firmware `.bin` ditaruh sendiri di folder ini — tidak disertakan di repo.

## Apa yang sudah diporting (semua sudah teruji di ONT nyata)

| Fitur asli | Perintah baru | File |
|---|---|---|
| Backup config (tombol Download) | `backup` | `steps/modem_http.py` |
| Upload `defaultconfig.xml` via web | `upload-xml` | `steps/modem_http.py` |
| Tunggu reboot 1-2 menit | `wait-reboot` | `steps/wait_reboot.py` |
| **Flash `2 - R022.bin`** (dulu `TOOLS FLASHER.exe`+multicast) | **`flash-web <bin>`** | `steps/modem_http.py` |
| `3 - EquipmodeR022.bat` / `step 2 - 18.1.bat` | `equipmode` | `steps/telnet_client.py` |
| `4 - Epon Mode.bat` / `step 3 - 18.1 Epon.bat` | `epon --mode epon` | `steps/telnet_client.py` |
| `AIO.bat` | `aio` | — |
| `CommandTelnetUpstreamPort.txt` | `epon --mode gpon/xpon/lan1..4` | — |
| Set mode lewat web (tanpa telnet) | `upport-web --mode epon` | `steps/modem_http.py` |
| Reboot modem | `reboot` | `steps/telnet_client.py` |
| **Flash massal otomatis (station colok-cabut)** | **`batch`** | `steps/batch.py` |

**Fase 2 SELESAI:** flash ternyata bisa lewat halaman web **Firmware Upgrade** (`Firmwareupload.cgi`) — lihat `flash-web`. Jadi replikasi UDP multicast (`OntSoftwareBroadcaster`) **tidak diperlukan**. `upport-web` bisa set mode lewat web, tapi jalur utama tetap telnet (`epon`).

### Endpoint web UI asli (terverifikasi di EG8145V5)

| Fungsi | Endpoint |
|---|---|
| Login token-persist | `POST /asp/GetRandCount.asp` lalu `POST /login.cgi` (koneksi sama) |
| Halaman config | `GET /html/ssmp/cfgfile/cfgfile.asp` → ambil `onttoken` (+ `RequestToken` **kalau ada**) |
| Upload config | `POST <form action>` = `/html/ssmp/cfgfile/cfgfileupload.cgi?RequestFile=html/ssmp/reset/reset.asp&FileType=config` (field `onttoken` + `browse`) |
| Backup config | `POST /html/ssmp/cfgfile/cfgfiledown.cgi?&RequestFile=html/ssmp/cfgfile/cfgfile.asp` (body `x.X_HW_Token=<onttoken>`) → `hw_ctree.xml` |
| Upload firmware | `POST <form action>` = `/html/ssmp/fireware/Firmwareupload.cgi?RequestFile=/html/ssmp/reset/reset.asp&FileType=image` (field `onttoken` + `browse`) |
| Set upport mode | `POST /html/ssmp/mainupportcfg/set.cgi?...&x=InternetGatewayDevice.DeviceInfo` (`x.X_HW_UpPortMode`, `x.X_HW_UpPortID`, `x.X_HW_Token`) |
| Reboot | `y=InternetGatewayDevice.X_HW_DEBUG.SMP.DM.ResetBoard` |

> **Adaptif antar-versi firmware.** URL upload **tidak di-hardcode**: diambil dari
> `<form action="...">` pada halaman itu sendiri (form `fr_uploadSetting` /
> `fr_uploadImage`), dengan fallback ke URL standar.
> `RequestToken` **opsional** — firmware lama (`V5R020C10S212`) memakainya,
> firmware R022 baru (`V5R022C10S167`) **tidak** (hanya `onttoken`).
> Ini yang dulu bikin gagal `RequestToken tidak ditemukan` di modem R022.
> Hati-hati juga: `cfgfileupload.cgi` vs `ptvdfcfgfileupload.cgi` (pencocokan
> pakai batas kata supaya tidak tertukar).

## Syarat

- Python 3.8+ (Termux: `pkg install python`)
- Tidak perlu `pip install` tambahan (hanya stdlib)
- Laptop/HP harus satu subnet dengan modem: `192.168.100.2/24` atau `192.168.18.2/24`
- Modem Huawei ONT terhubung via LAN

## Cara Pakai

### Linux PC

```bash
cd 5v5-flasher-v2/flasher
python3 flasher.py detect
python3 flasher.py backup                    # backup config dulu (aman)
python3 flasher.py upload-xml defaultconfig.xml
python3 flasher.py --host 192.168.100.1 wait-reboot
python3 flasher.py --host 192.168.100.1 equipmode
# tunggu reboot...
python3 flasher.py --host 192.168.100.1 epon --mode epon

# atau sekaligus:
python3 flasher.py --host 192.168.100.1 aio
python3 flasher.py --host auto full --xml defaultconfig.xml

# alternatif lewat web (tanpa telnet):
python3 flasher.py --host 192.168.18.1 flash-web "2 - R022.bin"
python3 flasher.py --host 192.168.18.1 upport-web --mode epon
```

### Termux Android

```bash
pkg update && pkg install python termux-tools -y
cd /sdcard/Download/flasher   # atau tempat kamu copy folder flasher/
python3 flasher.py detect
python3 flasher.py --host 192.168.100.1 aio
```

> Termux perlu akses storage: `termux-setup-storage`, lalu copy folder `flasher` ke `~/` atau `/sdcard/`

## Daftar Perintah

```
python3 flasher.py --help
python3 flasher.py detect                          # cari modem di 192.168.18.1 / 192.168.100.1
python3 flasher.py backup [--out file.bin] [--host IP]   # download config (aman)
python3 flasher.py upload-xml <file.xml> [--host IP]
python3 flasher.py wait-reboot [--host IP]
python3 flasher.py equipmode [--host IP] [--no-wait]
python3 flasher.py epon [--host IP] [--mode epon|gpon|xpon|lan1..4]
python3 flasher.py aio [--host IP]                # equipmode + epon
python3 flasher.py full [--xml file] [--bin file] # alur lengkap step.md
python3 flasher.py flash-web <file.bin> [--host IP]      # upload firmware via web (= pengganti .exe)
python3 flasher.py upport-web [--mode epon] [--host IP]  # set mode via web (tanpa telnet)
python3 flasher.py reboot [--host IP]             # reboot modem via telnet
python3 flasher.py batch [--xml f] [--bin f] [--bin-r020 f] [--bin-r022 f]   # MODE STATION: proses modem otomatis satu per satu
python3 flasher.py flash <file.bin>               # STUB lama (UDP multicast, tidak dipakai)
```

`--host auto` (default) akan auto-detect. Isi manual contoh: `--host 192.168.18.1`

## Mode Station Otomatis (`batch`)

Untuk flashing massal: tinggal **colok-cabut** modem, sisanya otomatis.

```bash
python3 flasher.py batch
# atau: python3 flasher.py batch --xml defaultconfig.xml --bin "2 - R022.bin"
# pilih firmware sesuai tipe modem:
#   python3 flasher.py batch --bin-r020 R020.bin --bin-r022 "2 - R022.bin"
# tes aman (tanpa mengubah modem): python3 flasher.py batch --dry-run
# proses 3 modem lalu berhenti:   python3 flasher.py batch --limit 3
# proses 1 modem saja:            python3 flasher.py batch --once
```

Alur per modem:

```
tunggu modem terpasang
  -> login -> baca Serial Number (kunci anti-dobel) + versi firmware
  -> pilih file firmware sesuai versi (R020 / R022)
  -> backup config asli ke backup/<SN>/hw_ctree_awal_*.bin
  -> upload config default 1_1010.xml
  -> flash <firmware>.bin via web  (telnet jadi aktif)
  -> equipmode (EquipMode.sh on + restorehwmode.sh)
  -> set EPON (set upport mode 2 upportid 0x102001)
  -> verifikasi mode == 2 (+ cek versi firmware berubah / tidak)
  -> cetak "SILAKAN CABUT MODEM INI, COLOK MODEM BERIKUTNYA" + beep
  -> tunggu modem dicabut -> tunggu modem baru -> ULANG
```

> **Web UI mati di fase equip mode.** Setelah `EquipMode.sh on`, port 80
> tidak dilayani (hanya telnet 23). Jadi step equipmode & EPON menunggu lewat
> **telnet** (`wait_for_telnet`), bukan HTTP. Kalau GUI tidak bisa dibuka di
> fase ini, itu normal — jalankan `flasher.py epon --mode epon` untuk
> menghidupkan web kembali.
>
> Semua penungguan di `batch` punya **timeout**: kalau modem tidak kembali,
> status dicatat `failed` dengan keterangan jelas (tidak menggantung selamanya).

- Modem dengan **Serial Number sama tidak akan diproses 2x** (jika masih tercolok, ditolak dan diminta cabut).
- Setiap modem dicatat di `backup/batch_log.csv` (SN, model, versi awal, versi setelah flash, versi akhir, MAC, hasil) dan konfigurasi aslinya disimpan per-serial.
- Ctrl+C kapan saja untuk berhenti (ringkasan tetap dicetak).

## Tampilan Terminal

Semua perintah otomatis memakai tampilan berwarna + banner + indikator STEP
(modul `steps/ui.py`, murni lapisan tampilan — logika tidak diubah):

- Di terminal asli: banner besar, warna, progress bar, spinner, kotak alert.
- Kalau output dipipe ke file (bukan TTY): otomatis jadi teks polos.
- Kalau console tidak mendukung Unicode (`cmd.exe` lama): otomatis pakai ASCII.
- Matikan paksa dengan `--plain` (boleh ditaruh di mana saja) atau `NO_COLOR=1`.
- Paksa nyala saat dipipe (mis. untuk demo): `FLASHER_UI=1`.

```bash
python3 flasher.py --plain batch       # output polos
python3 flasher.py batch | tee log.txt # otomatis polos saat dipipe
```

## Penjelasan Tiap Step

### 1. detect
Ping + GET `/` ke `192.168.18.1` dan `192.168.100.1`, lalu coba login probe dengan `Epadmin/adminEp` dan `telecomadmin/admintelecom`.

### 1b. backup
Login, ambil `onttoken` dari halaman config, lalu POST ke `cfgfiledown.cgi`. Hasilnya file `hw_ctree.xml` (config berjalan) disimpan ke folder `backup/`. Aman & read-only — sebaiknya lakukan sebelum langkah apa pun yang mengubah modem.

### 2. upload-xml
Login token-persist (`GetRandCount.asp` + `login.cgi`), buka `/html/ssmp/cfgfile/cfgfile.asp` untuk ambil `onttoken` (dan `RequestToken` kalau firmware memakainya), lalu ambil URL upload dari `<form action>` halaman tersebut dan POST `multipart/form-data` (field `onttoken` + `browse`). Modem akan reboot memakai config baru.

### 2b. flash-web  (ini pengganti `TOOLS FLASHER.exe`)
Login, buka `/html/ssmp/fireware/firmware.asp` untuk ambil `onttoken`, lalu POST `multipart/form-data` (field `browse`) ke `Firmwareupload.cgi?RequestFile=/html/ssmp/reset/reset.asp&FileType=image`. Kalau diterima, respons berisi `UpgradeInfoSuccess` (`ok.gif`). Setelah ini **telnet (port 23) aktif** dan password web berubah ke `telecomadmin/admintelecom`.

### 3. wait-reboot
Polling: tunggu host mati (ping gagal) → tunggu ping hidup lagi → tunggu port 23 (telnet) dan 80 (web) terbuka.

### 4. equipmode
Telnet `root/admin` → `su` → `shell` → `EquipMode.sh on` → `sudo restorehwmode.sh` → `reset`. Implementasi raw socket dengan handling IAC telnet (menggantikan VBS SendKeys).

### 5. epon
Telnet → `set upport mode 2 upportid 0x102001` (EPON) → `EquipMode.sh off` → `reboot`. Mode lain: `gpon (1)`, `xpon (4)`, `lan1..4 (3)`.

## Hasil uji END-TO-END di ONT nyata (29 Sep 2026) — BERHASIL ✅

Diuji langsung pada ONT tester: **Huawei EG8145V5** (USB-LAN, laptop di-static ke `192.168.100.2/24` + `192.168.18.2/24`).
**Seluruh workflow `step.md` berhasil dijalankan HANYA dengan Python (tanpa Windows, tanpa `TOOLS FLASHER.exe`, tanpa UDP multicast).**

Diuji pada **dua modem EG8145V5 dengan dua versi firmware berbeda** — dua-duanya sukses:

| | Modem #1 | Modem #2 |
|---|---|---|
| Serial Number | `HWTC9A1892AF` | `HWTC83CEDFB2` |
| Software | `V5R020C10S212` | `V5R022C10S167` |
| MAC | `98:F0:83:83:F0:A8` | `08:02:05:E9:79:34` |
| Login awal | `Epadmin/adminEp` @ `192.168.18.1` | `Epadmin/adminEp` @ `192.168.18.1` |
| `RequestToken` di form upload | ada | **tidak ada** (lihat catatan) |
| Hasil akhir | `UpPortMode = 2` (EPON) ✅ | `upport mode=2` (EPON) ✅ |
| Cara jalan | `flasher.py aio` + `epon` manual | **`flasher.py batch --once` (otomatis penuh, 4,8 menit)** ✅ |

| Langkah step.md | Perintah port | Hasil |
|---|---|---|
| 1. Detect + login | `detect` | ✅ ONT di `192.168.18.1`, `Epadmin/adminEp` |
| 1b. Backup | `backup` | ✅ `hw_ctree.xml` ~182 KB tersimpan |
| 2. Upload `1_1010.xml` | `upload-xml defaultconfig.xml` | ✅ via `cfgfileupload.cgi`, ONT reboot → `192.168.100.1`, SSID jadi `WirelessNet`, `X_HW_UpPortMode` jadi `4` (XPON) |
| 3-5. Flash `2 - R022.bin` | `flash-web "2 - R022.bin"` | ✅ via `Firmwareupload.cgi` → halaman sukses (`ok.gif`); **port 23 (telnet) langsung terbuka** |
| 7. EquipMode | `equipmode` | ✅ `EquipMode.sh on` + `sudo restorehwmode.sh` → `success!`, reboot |
| 8. EPON | `epon --mode epon` | ✅ `set upport mode 2 upportid 0x102001` → `success!` + `EquipMode.sh off` |

**Verifikasi akhir:** halaman upport ONT melaporkan `stConfigPort(...,"Optical","2","1056769")` → **UpPortMode = 2 = EPON** ✅

Mode otomatis (`batch`) juga sudah diuji nyata: deteksi → login → baca SN → backup
per-serial → upload config → flash → equipmode → EPON → verifikasi, tanpa intervensi.

### Temuan penting
- **Flash via web UI diterima modem** → Fase 2 (UDP multicast / `TOOLS FLASHER.exe`) tidak diperlukan. `flash-web` sudah cukup.
  - ⚠️ **Catatan (29 Sep 2026)**: pada ONT `HWTC4F162DAC` (EG8145V5, pabrik `V500R020C10SPC195`), upload via web dilaporkan **sukses** tetapi `SoftwareVersion` **tidak berubah** (tetap `V5R020C10S195`, sama dengan versi pabriknya). Hal yang sama terlihat di `HWTC83CEDFB2` (pabrik `V500R022C10SPC167`, tetap R022). Jadi: **jangan anggap versi firmware pasti naik** — `batch` sekarang mencatat `software_after_flash` & `software_final` di `batch_log.csv` dan otomatis menandai bila versinya tidak berubah. Konversi **EPON tetap berhasil** karena itu urusan `set upport mode`, bukan firmware.
- `2 - R022.bin` = paket **HWNP resmi Huawei** (bertanda tangan), berisi `UpgradeCheck.xml` (semua chip-check `CheckEnable="0"`), `duit9rr.sh`, `TelnetEnable`, `ProductLineMode`. ONT menerimanya lewat web.
- Bukti terpasang: `/var/duit9rr.sh` (5811 B) & `/mnt/jffs2/ProductLineMode` ada, `/bin/EquipMode.sh` + `/bin/restorehwmode.sh` ada.
- **Kredensial web berubah setelah flash/`restorehwmode`**: dari **`Epadmin`/`adminEp`** → menjadi **`telecomadmin`/`admintelecom`**. (Kode `login_host`/`try_login_any_host` sudah mencoba keduanya.)
- **Endpoint upload berbeda antar-firmware.** `V5R020C10S212` memakai `RequestToken`; `V5R022C10S167` **tidak**. URL upload kini diambil otomatis dari `<form action>` halaman (lihat tabel endpoint) → tidak perlu ubah kode kalau ketemu firmware lain.
- 🔴 **Web UI MATI selama equip mode.** Setelah `EquipMode.sh on`, port 80 **tidak dilayani** — hanya telnet (23) + DNS (53). Ini **normal** (bukan modem rusak) dan persis seperti alur `.bat` asli yang tidak pernah membuka web di antara `3 - EquipmodeR022.bat` dan `4 - Epon Mode.bat`. Web baru kembali setelah `EquipMode.sh off`.
  - **Bug lama (sudah diperbaiki)**: `wait_for_modem()` adalah `while True` tanpa timeout yang hanya mengecek HTTP port 80 → `batch` menggantung **selamanya** di akhir step 6. Sekarang step 6 & 7 menunggu lewat **telnet** (`wait_for_telnet`), dan semua penungguan punya **timeout** + status `failed` yang jelas.
- **Tipe modem bermacam-macam**: `V300R020` (`HWTC9A1892AF`), `V500R020` (`HWTC4F162DAC`), `V500R022` (`HWTC83CEDFB2`). `batch` sekarang bisa memilih file firmware sesuai versi modem (`--bin-r020` / `--bin-r022`, atau otomatis dari `R020.bin` / `2 - R022.bin`). Ada juga safety-net: kalau 2 file firmware itu **identik** (biasanya salah copy/rename), tool memberi peringatan.
- Setelah reboot pasca `restorehwmode`, web UI sempat menampilkan `index.asp` = "Waiting..." (itu **redirector permanen**, bukan lock) dan login gagal selama beberapa detik → **tunggu 1-2 menit** sampai `login.cgi` mengembalikan cookie `sid`.
- Shell telnet bersifat **whitelist**: `ls`, `set`, `EquipMode.sh`, `restorehwmode.sh`, `reboot` jalan; `cat`, `whoami`, pipe `|`, dan `;` menghasilkan `ERROR::Command is not existed` / `ERROR::Input para is not right`.
  - Catatan: pada ONT yang masih di **equip mode**, `ls` di prompt `WAP>` menjawab `ERROR::Command is not existed` (whitelist beda) — itu normal, bukan tanda error flash.
- **Telnet tidak perlu sebelum flash**: port 23 memang baru kebuka setelah `2 - R022.bin` masuk. Jadi `flash-web` wajib sebelum `equipmode`/`epon`.

## Troubleshooting

- `Login gagal` → cek IP laptop satu subnet belum; sebelum flash pakai `Epadmin/adminEp`, **sesudah flash pakai `telecomadmin/admintelecom`**. Tunggu 1-2 menit setelah reboot.
- **`GUI modem tidak bisa dibuka` tapi ping + telnet jalan** → hampir pasti modem sedang **equip mode** (web memang dimatikan). Jalankan:
  `python3 flasher.py --host 192.168.100.1 epon --mode epon` (= `4 - Epon Mode.bat`) → web balik dalam hitungan detik.
- `Batch menggantung di step 5/6` → versi lama punya `wait_for_modem()` tanpa timeout. Pastikan sudah pakai versi ini (step 6/7 menunggu telnet).
- `Versi firmware tidak berubah` → upload web diterima tapi image tidak terpasang. Cek kolom `software_after_flash`/`software_final` di `batch_log.csv`; kalau perlu, jalur UDP multicast (`TOOLS FLASHER.exe`) atau file firmware yang benar (`--bin-r020`) masih tersedia sebagai cadangan.
- `Upload gagal` → buka web UI manual, F12 → Network → lihat URL sebenarnya, lalu lapor untuk update endpoint.
- `Telnet gagal` → telnet baru terbuka setelah `flash-web` sukses. Cek `ping 192.168.100.1` dan tes port 23.
- `Port 23 tidak terbuka` → tunggu 2-3 menit setelah upload firmware; kalau tetap tertutup, ulangi `flash-web` lalu `reboot`.
- `reset`/`reboot` lewat telnet memutus koneksi → itu normal (sudah ditangani sebagai sukses).

## Fase 2 (SELESAI — via web, tanpa multicast)

`flash-web` sudah terbukti menggantikan `TOOLS FLASHER.exe`. Jalur UDP multicast (`OntSoftwareBroadcaster`) tetap didokumentasikan sebagai cadangan, tapi **tidak lagi dibutuhkan**. Stub `flasher.py flash <bin>` hanya tinggal nama.

## Lisensi

Port ini untuk edukasi. Firmware/modem Huawei tetap tunduk pada lisensi Huawei. Gunakan dengan risiko sendiri, jangan untuk merusak jaringan orang lain.

