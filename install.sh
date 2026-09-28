#!/usr/bin/env sh
# ===========================================================================
#  5v5 FLASHER - pemasang sekali jalan untuk Linux / Android (Termux) / macOS
#
#  Pakai:
#      sh install.sh
#
#  Skrip ini:
#    1. mendeteksi sistem + manajer paket
#    2. memastikan Python 3.8+ dan pip ada (kalau belum ada, dipasang)
#    3. memasang paket proyek ini (opsional, tool ini tanpa dependensi runtime)
#    4. memasang pytest + menjalankan uji cepat
#
#  Aman dijalankan berulang: yang sudah terpasang akan dilewati.
# ===========================================================================
set -u

HERE=$(cd "$(dirname "$0")" 2>/dev/null && pwd) || exit 1
cd "$HERE" || exit 1

if [ -t 1 ]; then
    C_OK=$(printf '\033[32m'); C_IN=$(printf '\033[36m'); C_WR=$(printf '\033[33m')
    C_ER=$(printf '\033[31m'); C_R=$(printf '\033[0m')
else
    C_OK=; C_IN=; C_WR=; C_ER=; C_R=
fi

ok()   { printf '%s  [ OK ]%s %s\n'   "$C_OK" "$C_R" "$1"; }
info() { printf '%s  [ .. ]%s %s\n'   "$C_IN" "$C_R" "$1"; }
warn() { printf '%s  [ !! ]%s %s\n'   "$C_WR" "$C_R" "$1"; }
err()  { printf '%s  [FAIL]%s %s\n'   "$C_ER" "$C_R" "$1"; }
step() { printf '\n%s==> %s%s\n'      "$C_IN" "$1" "$C_R"; }
have() { command -v "$1" >/dev/null 2>&1; }

printf '\n%s5v5 FLASHER - pemasangan%s\n' "$C_IN" "$C_R"
printf 'Folder: %s\n' "$HERE"

# ---------------------------------------------------------------------------
# 1. Deteksi lingkungan
# ---------------------------------------------------------------------------
step "1/5  Deteksi sistem"

PM=""
PLATFORM=""
if [ -n "${PREFIX:-}" ] && have pkg; then
    PM="pkg";        PLATFORM="Termux / Android"
elif have apt-get; then
    PM="apt-get";    PLATFORM="Debian / Ubuntu / Kali / Mint"
elif have dnf; then
    PM="dnf";        PLATFORM="Fedora / RHEL"
elif have yum; then
    PM="yum";        PLATFORM="CentOS / RHEL lama"
elif have pacman; then
    PM="pacman";     PLATFORM="Arch / Manjaro"
elif have apk; then
    PM="apk";        PLATFORM="Alpine"
elif have brew; then
    PM="brew";       PLATFORM="macOS / Homebrew"
else
    PLATFORM="(manajer paket tidak dikenal)"
fi

SUDO=""
if [ "$(id -u 2>/dev/null || echo 0)" != "0" ] && have sudo; then SUDO="sudo"; fi

info "Sistem  : $PLATFORM"
info "Paket   : ${PM:-tidak terdeteksi}"
[ "$(uname -s 2>/dev/null)" = "Darwin" ] && info "Kernel  : macOS"

install_pkg() {
    [ -n "$PM" ] || return 1
    case "$PM" in
        pkg)     pkg install -y "$@" ;;
        apt-get) $SUDO apt-get update -y >/dev/null 2>&1 || true
                 $SUDO apt-get install -y "$@" ;;
        dnf)     $SUDO dnf install -y "$@" ;;
        yum)     $SUDO yum install -y "$@" ;;
        pacman)  $SUDO pacman -S --noconfirm --needed "$@" ;;
        apk)     $SUDO apk add --no-cache "$@" ;;
        brew)    brew install "$@" ;;
        *)       return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# 2. Python 3.8+
# ---------------------------------------------------------------------------
step "2/5  Python"

PY=""
for c in python3 python; do
    if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
        PY="$c"
        break
    fi
done

if [ -n "$PY" ]; then
    ok "Python $("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])') -> $(command -v "$PY")"
else
    warn "Python 3.8+ tidak ditemukan. Mencoba memasang..."
    case "$PM" in
        pkg)     install_pkg python ;;
        apt-get) install_pkg python3 ;;
        dnf|yum) install_pkg python3 ;;
        pacman)  install_pkg python ;;
        apk)     install_pkg python3 ;;
        brew)    install_pkg python3 ;;
        *)
            err "Pasang Python 3.8+ dulu: https://www.python.org/downloads/"
            exit 1
            ;;
    esac
    for c in python3 python; do
        if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
            PY="$c"; break
        fi
    done
    if [ -n "$PY" ]; then
        ok "Python terpasang: $("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
    else
        err "Pemasangan Python gagal. Pasang manual lalu ulangi skrip ini."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# 3. pip
# ---------------------------------------------------------------------------
step "3/5  pip"

if "$PY" -m pip --version >/dev/null 2>&1; then
    ok "pip sudah ada: $("$PY" -m pip --version 2>/dev/null | cut -d' ' -f1-2)"
else
    info "pip belum ada. Mencoba via ensurepip..."
    "$PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
    if ! "$PY" -m pip --version >/dev/null 2>&1; then
        case "$PM" in
            apt-get) install_pkg python3-pip ;;
            dnf|yum) install_pkg python3-pip ;;
            pacman)  install_pkg python-pip ;;
            apk)     install_pkg py3-pip ;;
            pkg)     install_pkg python ;;
            *)       : ;;
        esac
    fi
    if "$PY" -m pip --version >/dev/null 2>&1; then
        ok "pip terpasang"
    else
        warn "pip tidak tersedia. Tidak masalah - tool ini tanpa dependensi,"
        warn "langsung bisa dijalankan: $PY flasher/flasher.py --help"
    fi
fi

pip_install() {
    "$PY" -m pip install --quiet "$@" >/dev/null 2>&1 && return 0
    "$PY" -m pip install --quiet --user "$@" >/dev/null 2>&1 && return 0
    "$PY" -m pip install --quiet --break-system-packages "$@" >/dev/null 2>&1 && return 0
    return 1
}

# ---------------------------------------------------------------------------
# 4. Paket proyek + pytest
# ---------------------------------------------------------------------------
step "4/5  Paket proyek & dependensi uji"

if "$PY" -m pip --version >/dev/null 2>&1; then
    if pip_install -e .; then
        ok "Terpasang (editable). Perintah '5v5-flasher' tersedia."
    else
        warn "Lewati 'pip install -e .' (tidak wajib)."
    fi
    if "$PY" -c 'import pytest' >/dev/null 2>&1; then
        ok "pytest sudah ada"
    elif pip_install -r requirements-dev.txt; then
        ok "pytest terpasang"
    else
        warn "pytest gagal dipasang - uji otomatis dilewati (tidak wajib untuk memakai tool)."
    fi
else
    info "Tanpa pip: tidak ada yang perlu dipasang. Tool ini murni standard library."
fi

# ---------------------------------------------------------------------------
# 5. Uji cepat
# ---------------------------------------------------------------------------
step "5/5  Uji cepat"

if "$PY" flasher/flasher.py --plain --help >/dev/null 2>&1; then
    ok "flasher.py jalan (--help OK)"
else
    err "flasher.py gagal dijalankan. Cek pesan di atas."
    exit 1
fi

if "$PY" -c 'import pytest' >/dev/null 2>&1; then
    if "$PY" -m pytest -q >/dev/null 2>&1; then
        ok "Uji otomatis lolos ($("$PY" -m pytest -q 2>/dev/null | tail -n 1))"
    else
        warn "Ada uji yang gagal - jalankan '$PY -m pytest -q' untuk detail."
    fi
else
    info "pytest tidak ada - lewati uji otomatis"
fi

printf '\n%sSelesai.%s\n' "$C_OK" "$C_R"
cat <<EOF

Langkah berikutnya (colok ONT Huawei ke LAN, laptop/HP di 192.168.100.2 atau 192.168.18.2 /24):

    $PY flasher/flasher.py detect            # cek modem terdeteksi
    $PY flasher/flasher.py batch             # MODE STASIUN otomatis (colok -> proses -> ganti)

Firmware .bin (mis. "2 - R022.bin") taruh di folder flasher/.
Detail lengkap: flasher/README.md
EOF
