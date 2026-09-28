"""Helper bersama untuk unit test - pengganti socket / waktu, tanpa hardware."""


class FakeSock:
    """Pengganti socket: merekam semua data yang dikirim."""

    def __init__(self):
        self.sent = []
        self.closed = False

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


class FakeClock:
    """
    Pengganti modul `time` untuk test.

    - `sleep()` tidak menunggu apa-apa (test jadi cepat).
    - `time()` selalu maju `step` detik setiap dipanggil, sehingga loop
      `while time.time() < deadline` tetap berakhir dengan sendirinya.
    """

    def __init__(self, step=1.0):
        self.t = 0.0
        self.step = step

    def time(self):
        self.t += self.step
        return self.t

    def sleep(self, seconds):
        pass

    def strftime(self, fmt):
        return "00:00:00"


class NoSleepTime:
    """
    Modul `time` asli, tapi `sleep()` langsung kembali.

    Dipakai oleh test yang butuh `time.strftime()` sungguhan (mis. pembuatan
    nama file backup) tetapi tidak mau menunggu jeda 5-10 detik milik program.
    """

    def __init__(self):
        import time as _real

        self._real = _real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def sleep(self, seconds):  # noqa: D102 - sengaja no-op
        pass
