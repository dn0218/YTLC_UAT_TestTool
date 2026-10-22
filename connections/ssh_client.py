"""SSH connection wrapper for executing bill-run scripts remotely."""
import re
import time

import paramiko

from core.config import AppConfig
from core.errors import SSHConnectionError
from connections.base import BaseConnection

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (cursor moves, screen clears, ...)."""
    return _ANSI_RE.sub("", text)


# Output line prefixes that are considered meaningful progress markers.
STEP_PREFIXES = ("Step 1", "Step 2", "Step 3", "Start Call")
STEP_MARKERS = ("successWait 10 seconds for job running",)


class SSHClient(BaseConnection):
    """Wraps paramiko.SSHClient with reconnect and a streaming exec API."""

    def __init__(self, config: AppConfig):
        super().__init__()
        self._config = config

    def get_connection(self) -> paramiko.SSHClient:
        if self._conn is not None:
            return self._conn

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self._config.ssh['host'],
                username=self._config.ssh['username'],
                password=self._config.ssh['password'],
                timeout=10
            )
        except Exception as e:
            client.close()
            raise SSHConnectionError(f"SSH connection failed: {e}") from e
        self._conn = client
        return self._conn

    def exec_command_stream(self, command: str, on_line=None, is_meaningful=None):
        """Run a remote command, streaming each stdout line to `on_line(line)`.

        Only lines for which is_meaningful(line) is True are forwarded
        (defaults to the bill-run step markers).
        """
        if is_meaningful is None:
            def is_meaningful(line: str) -> bool:
                return (any(line.startswith(p) for p in STEP_PREFIXES)
                        or any(m in line for m in STEP_MARKERS))

        ssh = self.get_connection()
        try:
            # NOTE: with get_pty=True, stderr is merged into stdout, so a
            # program that writes the same log line to BOTH streams shows it
            # twice. We already filter which lines get forwarded via
            # is_meaningful, and RecurrRate's begin/end markers matched from
            # either stream - reading only stdout is not possible under a PTY,
            # so deduplicate consecutive identical lines instead.
            stdin, stdout, stderr = ssh.exec_command(command, get_pty=True)
            last = None
            for line in iter(stdout.readline, ""):
                clean = line.strip()
                if clean == last:
                    continue  # skip the immediate duplicate copy
                last = clean
                if is_meaningful(clean) and on_line:
                    on_line(clean)
            exit_status = stdout.channel.recv_exit_status()
            stdin.close()
            stdout.close()
            stderr.close()
            return exit_status
        except SSHConnectionError:
            raise
        except Exception as e:
            self.close()
            raise SSHConnectionError(f"SSH command execution failed: {e}") from e

    # ------------------------------------------------------------------
    # Interactive shell (for console tools like OCS "mdbtt")
    # ------------------------------------------------------------------
    def open_interactive_shell(self, term="vt100", width=500, height=50):
        """Open a persistent PTY channel for interactive console programs.

        Returns the paramiko Channel. Caller drives it via send_line() /
        read_until() on this class, and MUST close it via
        close_interactive_shell() when done.
        """
        ssh = self.get_connection()
        try:
            chan = ssh.invoke_shell(term=term, width=width, height=height)
            chan.settimeout(5)
            self._interactive_chan = chan
            return chan
        except Exception as e:
            self.close()
            raise SSHConnectionError(
                f"Failed to open interactive shell: {e}") from e

    def close_interactive_shell(self):
        chan = getattr(self, "_interactive_chan", None)
        if chan is not None:
            try:
                chan.close()
            except Exception:
                pass
            self._interactive_chan = None

    def send_line(self, line: str):
        """Write one line (plus newline) to the interactive channel."""
        chan = getattr(self, "_interactive_chan", None)
        if chan is None or chan.closed:
            raise SSHConnectionError("Interactive shell is not open.")
        self._last_sent_line = (line or "").strip()
        chan.send(line + "\r\n")

    def read_until(self, patterns, timeout=30.0, on_line=None,
                   poll=0.2, echo_strip=True):
        """Read from the interactive channel until one of `patterns` appears.

        patterns  : iterable of plain-text markers (matched against the
                    tail of the accumulated buffer AND per finished line).
        timeout   : total seconds to wait before giving up.
        on_line   : optional callback fired once per finished line, with
                    the cleaned line as its only argument (used for live
                    console logging in the UI).
        echo_strip: drop the terminal echo of what we just sent (the PTY
                    echoes our command back at us).

        Returns (matched_pattern_or_None, full_buffer). A None match with
        an empty-ish buffer after timeout means "no prompt seen".
        """
        chan = getattr(self, "_interactive_chan", None)
        if chan is None or chan.closed:
            raise SSHConnectionError("Interactive shell is not open.")

        patterns = list(patterns)
        deadline = time.time() + timeout
        buf = ""
        seen_lines = []

        def _feed(chunk: str):
            nonlocal buf
            buf += chunk
            while "\n" in buf:
                raw_line, buf = buf.split("\n", 1)
                clean = strip_ansi(raw_line.rstrip("\r")).strip()
                if not clean:
                    continue
                # Drop the echo of the command we sent (PTY echoes input).
                if echo_strip and seen_echo and clean == seen_echo:
                    continue
                if echo_strip and seen_echo and clean == seen_echo + ";":
                    continue
                seen_lines.append(clean)
                if on_line:
                    try:
                        on_line(clean)
                    except Exception:
                        pass

        # Track the last line we sent so its echo can be removed.
        seen_echo = getattr(self, "_last_sent_line", None)

        while time.time() < deadline:
            got = False
            while chan.recv_ready():
                data = chan.recv(4096)
                if not data:
                    break
                _feed(data.decode("utf-8", errors="replace"))
                got = True
            if got:
                tail = buf[-512:]
                for p in patterns:
                    if p in tail or p in "\n".join(seen_lines[-5:]):
                        return p, "\n".join(seen_lines)
            else:
                # Nothing new; also check accumulated buffer between bursts.
                tail = buf[-512:]
                for p in patterns:
                    if p in tail or p in "\n".join(seen_lines[-5:]):
                        return p, "\n".join(seen_lines)
                time.sleep(poll)

        return None, "\n".join(seen_lines)
