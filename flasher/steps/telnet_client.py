"""
telnet_client.py - Raw socket telnet client tanpa dependensi eksternal.
Kompatibel Linux + Termux (Python stdlib saja).
Menggantikan VBS SendKeys di file .bat.
"""
import socket
import select
import time
import re


class TelnetClient:
    def __init__(self, host, port=23, timeout=10, verbose=True):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.verbose = verbose
        self.sock = None
        self._buf = ""

    def log(self, msg, level="INFO"):
        if self.verbose:
            prefix = {"INFO": "[*]", "OK": "[OK]", "WARN": "[!]", "ERR": "[ERR]", "SEND": "[>>]", "RECV": "[<<]"}
            print(f"{prefix.get(level, '[*]')} {msg}")

    def connect(self):
        self.log(f"Connecting ke {self.host}:{self.port} ...")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(1.0)  # short timeout for recv loop
        self.log(f"Terhubung ke {self.host}:{self.port}", "OK")
        # consume banner with IAC filtering (simpan ke buffer agar login bisa lihat prompt)
        time.sleep(0.5)
        data = self._recv_available()
        if data:
            self._buf += data
            self.log(f"Banner: {repr(data[:200])}", "RECV")
        return True

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            self.log("Koneksi telnet ditutup")

    def _handle_iac(self, data: bytes) -> bytes:
        """Filter telnet IAC negotiation, reply WONT/DONT to avoid hanging."""
        out = bytearray()
        i = 0
        while i < len(data):
            if data[i] == 255:  # IAC
                if i + 1 >= len(data):
                    i += 1
                    continue
                cmd = data[i + 1]
                # Commands: WILL 251, WONT 252, DO 253, DONT 254
                if cmd in (251, 252, 253, 254):
                    if i + 2 >= len(data):
                        i += 2
                        continue
                    opt = data[i + 2]
                    # Respond: DO -> WONT, WILL -> DONT
                    if cmd == 251:  # WILL -> DONT
                        try:
                            self.sock.sendall(bytes([255, 254, opt]))
                        except Exception:
                            pass
                    elif cmd == 253:  # DO -> WONT
                        try:
                            self.sock.sendall(bytes([255, 252, opt]))
                        except Exception:
                            pass
                    i += 3
                elif cmd == 255:  # IAC IAC -> escaped 255
                    out.append(255)
                    i += 2
                else:
                    i += 2
            else:
                out.append(data[i])
                i += 1
        return bytes(out)

    def _recv_available(self) -> str:
        """Recv all available data with IAC filtering, return decoded text."""
        chunks = []
        end = time.time() + 0.5
        while time.time() < end:
            r, _, _ = select.select([self.sock], [], [], 0.3)
            if not r:
                break
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                break
            if not data:
                break
            filtered = self._handle_iac(data)
            if filtered:
                chunks.append(filtered)
                end = time.time() + 0.4  # extend wait if data keeps coming
        if not chunks:
            return ""
        raw = b"".join(chunks)
        # try utf-8, fallback latin1
        try:
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return raw.decode("latin-1", errors="ignore")

    def _send_line(self, line: str):
        self.log(f"{line}", "SEND")
        self.sock.sendall((line + "\r\n").encode("utf-8"))

    def expect(self, patterns, timeout=8):
        """
        Tunggu sampai salah satu pattern muncul.
        patterns: str atau list[str] (regex, case-insensitive)
        return: (matched_text, full_buffer) atau (None, buffer) jika timeout
        """
        if isinstance(patterns, str):
            patterns = [patterns]
        compiled = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]
        deadline = time.time() + timeout
        # mulai dari sisa buffer pemanggilan sebelumnya + data yang baru masuk
        buf = self._buf
        self._buf = ""
        buf += self._recv_available()
        for c in compiled:
            if c.search(buf):
                self.log(f"Dapat: {repr(buf[-120:])}", "RECV")
                return c.pattern, buf
        while time.time() < deadline:
            chunk = self._recv_available()
            if chunk:
                buf += chunk
                # keep buffer reasonable
                if len(buf) > 16384:
                    buf = buf[-8192:]
                for c in compiled:
                    if c.search(buf):
                        self.log(f"Dapat: {repr(chunk[:120])}", "RECV")
                        return c.pattern, buf
            time.sleep(0.2)
        # simpan sisa buffer supaya pemanggilan berikutnya masih bisa memakainya
        self._buf = buf[-4096:]
        return None, buf

    def login(self, user="root", password="admin", login_timeout=6):
        """Login sequence: tunggu 'Login:' -> kirim user -> tunggu 'Password:' -> kirim password."""
        # Huawei ONT usually shows 'Login:' prompt after connect
        pat, buf = self.expect(r"login|username|user name", timeout=login_timeout)
        if pat is None:
            # prompt tidak terlihat (mungkin sudah terpakai), tetap coba kirim user
            self.log("Prompt login tidak terdeteksi, coba kirim user langsung", "WARN")
            time.sleep(0.5)
        self._send_line(user)
        pat, buf = self.expect(r"password", timeout=6)
        if pat is None:
            self.log(f"Prompt password tidak muncul, buffer: {repr(buf[-200:])}", "WARN")
            # still try sending password
        self._send_line(password)
        # tunggu prompt Huawei: WAP> atau SU_WAP> atau #
        pat, buf = self.expect(r"WAP>|SU_WAP>|#", timeout=8)
        # deteksi kegagalan dari ISI buffer (bukan dari string pattern!)
        if re.search(r"incorrect|failed|invalid password", buf, re.IGNORECASE):
            self.log(f"Login gagal ke {self.host} dengan {user}/{password}: {repr(buf[-200:])}", "ERR")
            return False
        # Huawei may need extra newline to show prompt
        if pat is None:
            self.log(f"Tidak ada prompt setelah login, buffer: {repr(buf[-300:])}", "WARN")
            # try sending empty to trigger prompt
            self._send_line("")
            pat, buf = self.expect(r"WAP>|SU_WAP>|#|>", timeout=4)
        self.log(f"Login OK ke {self.host} sebagai {user}", "OK")
        return True

    def run_commands(self, commands, prompt_pattern=r"WAP>|SU_WAP>|#|>", cmd_timeout=10, inter_delay=0.5):
        """
        Jalankan list commands satu per satu, tunggu prompt tiap selesai.
        commands: list[str]
        return: dict hasil per command {cmd: (success, output)}
        """
        results = {}
        for cmd in commands:
            low = cmd.strip().lower()
            try:
                self._send_line(cmd)
            except Exception as e:
                # koneksi putus saat mengirim -> normal untuk reboot/reset/quit
                if low in ("quit", "exit", "reboot", "reset"):
                    results[cmd] = (True, f"koneksi putus (normal): {e}")
                    self.log(f"OK (disconnect): {cmd}", "OK")
                else:
                    results[cmd] = (False, str(e))
                break
            time.sleep(inter_delay)
            try:
                pat, buf = self.expect(prompt_pattern, timeout=cmd_timeout)
            except Exception as e:
                if low in ("quit", "exit", "reboot", "reset"):
                    results[cmd] = (True, f"koneksi putus (normal): {e}")
                    self.log(f"OK (disconnect): {cmd}", "OK")
                else:
                    results[cmd] = (False, str(e))
                break
            success = pat is not None
            # jika quit/exit/reboot/reset tidak balik prompt karena disconnect, itu dianggap sukses
            if low in ("quit", "exit", "reboot", "reset"):
                success = True
            results[cmd] = (success, buf)
            if success:
                self.log(f"OK: {cmd}", "OK")
            else:
                self.log(f"Timeout/could not confirm: {cmd} | buf={repr(buf[-200:])}", "WARN")
            # small delay between commands
            time.sleep(inter_delay)
        return results


def run_sequence(host, user, password, commands, verbose=True, retries=3):
    """
    Helper: connect -> login -> jalankan commands -> close, dengan retry.
    Return: (success, hasil)
    """
    last = ""
    for attempt in range(retries):
        try:
            c = TelnetClient(host, verbose=verbose)
            c.connect()
            if not c.login(user, password):
                c.close()
                last = "login gagal"
                if verbose:
                    print(f"[!] Percobaan {attempt+1} login gagal, retry...")
                time.sleep(3)
                continue
            res = c.run_commands(commands)
            c.close()
            return all(v[0] for v in res.values()), res
        except Exception as e:
            last = str(e)
            if verbose:
                print(f"[!] Percobaan {attempt+1} error: {e}")
            time.sleep(3)
    return False, last


def quick_telnet(host, user, password, commands, port=23, verbose=True):
    """Helper satu-kali: connect -> login -> run commands -> close."""
    c = TelnetClient(host, port=port, verbose=verbose)
    try:
        c.connect()
        if not c.login(user, password):
            return False
        # naive su step if needed - caller should include 'su' in commands jika perlu
        res = c.run_commands(commands)
        # check all success
        all_ok = all(v[0] for v in res.values())
        return all_ok
    finally:
        c.close()
