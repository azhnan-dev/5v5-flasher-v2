"""
Konfigurasi pytest untuk 5v5-flasher.

Test bisa dijalankan langsung dari root repo, TANPA meng-install apa pun:

    python -m pytest

File ini menambahkan folder `flasher/` ke sys.path sehingga `import steps...`
dan `import flasher` bekerja apa adanya (sesuai cara program dijalankan sehari-hari).
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FLASHER_DIR = os.path.join(ROOT, "flasher")

if FLASHER_DIR not in sys.path:
    sys.path.insert(0, FLASHER_DIR)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


@pytest.fixture(autouse=True)
def _plain_ui():
    """Semua test memakai tampilan polos (tanpa ANSI/banner) supaya output stabil."""
    from steps import ui

    ui.set_plain(True)
    yield
