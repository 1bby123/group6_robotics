"""
Runs on the Mac inside game.py. Opens a TCP socket to pi_server.py on the
Raspberry Pi and sends movement commands
"""

import socket
import time
from dataclasses import dataclass
from typing import Optional


# Controller states
STATE_IDLE    = "idle"
STATE_MOVING  = "moving"
STATE_DONE    = "done"
STATE_ERROR   = "error"


@dataclass
class ClawbotStatus:
    state: str = STATE_IDLE
    last_status_msg: str = ""
    error_reason: Optional[str] = None


class ClawbotController:
    """Base class. Subclass and implement _send_line and _poll_lines."""

    def __init__(self):
        self.status = ClawbotStatus()



    def connect(self):
        raise NotImplementedError

    def close(self):
        pass

    def place(self, row, col):
        """Kick off a PLACE command."""
        if self.status.state == STATE_MOVING:
            print("[clawbot] WARN: place() called while already moving")
            return False
        self.status = ClawbotStatus(state=STATE_MOVING)
        self._send_line(f"PLACE {row} {col}")
        return True

    def home(self):
        self.status = ClawbotStatus(state=STATE_MOVING)
        self._send_line("HOME")

    def calibrate(self, row, col):
        self.status = ClawbotStatus(state=STATE_MOVING)
        self._send_line(f"CALIBRATE {row} {col}")

    def ping(self):
        self._send_line("PING")

    def emergency_stop(self):
        self._send_line("STOP")
        self.status = ClawbotStatus(state=STATE_ERROR, error_reason="emergency_stop")

    def poll(self):
        """Read any pending responses from the brain. Call every frame."""
        for line in self._poll_lines():
            self._handle_response(line)

    def is_idle(self):
        return self.status.state == STATE_IDLE

    def is_moving(self):
        return self.status.state == STATE_MOVING

    def is_done(self):
        return self.status.state == STATE_DONE

    def is_error(self):
        return self.status.state == STATE_ERROR

    def reset_state(self):
        """Called after game.py has consumed a DONE/ERROR result."""
        if self.status.state in (STATE_DONE, STATE_ERROR):
            self.status = ClawbotStatus(state=STATE_IDLE)

    #Response Handling

    def _handle_response(self, line):
        if not line:
            return
        parts = line.split(None, 1)
        tag = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""

        if tag == "DONE":
            print(f"[clawbot] DONE")
            self.status.state = STATE_DONE
        elif tag == "ERROR":
            print(f"[clawbot] ERROR: {rest}")
            self.status.state = STATE_ERROR
            self.status.error_reason = rest or "unknown"
        elif tag == "STATUS":
            print(f"[clawbot] {rest}")
            self.status.last_status_msg = rest
        elif tag == "READY":
            print(f"[clawbot] brain ready")
        elif tag == "PONG":
            print(f"[clawbot] PONG")
        else:
            print(f"[clawbot] <?> {line}")

    # Subclass hooks

    def _send_line(self, line):
        raise NotImplementedError

    def _poll_lines(self):
        """Return a list of zero or more complete lines received since last poll."""
        raise NotImplementedError


# Network implementation

class NetworkClawbotController(ClawbotController):
    """Talks to pi_server.py over TCP."""

    def __init__(self, host, port=9999):
        super().__init__()
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self._recv_buf = b""

    def connect(self, timeout=5.0):
        print(f"[clawbot] connecting to {self.host}:{self.port}")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((self.host, self.port))
        except OSError as e:
            print(f"[clawbot] connect failed: {e}")
            raise
        s.setblocking(False)   # non-blocking for poll()
        self.sock = s
        print(f"[clawbot] connected")

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _send_line(self, line):
        if not self.sock:
            print("[clawbot] WARN: send without connection")
            return
        data = (line.rstrip("\n") + "\n").encode("ascii")
        try:
            self.sock.sendall(data)
            print(f"[clawbot] → {line}")
        except OSError as e:
            print(f"[clawbot] send failed: {e}")
            self.status.state = STATE_ERROR
            self.status.error_reason = f"send_failed_{e.errno}"

    def _poll_lines(self):
        if not self.sock:
            return []
        lines = []
        try:
            chunk = self.sock.recv(4096)
            if chunk == b"":
                print("[clawbot] connection closed by peer")
                self.status.state = STATE_ERROR
                self.status.error_reason = "disconnected"
                return []
            self._recv_buf += chunk
        except BlockingIOError:
            pass
        except OSError as e:
            print(f"[clawbot] recv failed: {e}")
            self.status.state = STATE_ERROR
            self.status.error_reason = f"recv_failed_{e.errno}"
            return []

        while b"\n" in self._recv_buf:
            line, self._recv_buf = self._recv_buf.split(b"\n", 1)
            text = line.decode("ascii", errors="replace").strip()
            if text:
                lines.append(text)
        return lines


# Mock implementation for development without hardware

class MockClawbotController(ClawbotController):
    """Fake clawbot for dev. Simulates a ~3 second placement then reports DONE."""

    def __init__(self, delay_sec=3.0):
        super().__init__()
        self.delay_sec = delay_sec
        self._command_start = 0.0
        self._pending_done = False
        self._status_sent = False

    def connect(self):
        print("[mock clawbot] ready")

    def _send_line(self, line):
        print(f"[mock clawbot] → {line}")
        if line.startswith("PLACE") or line.startswith("CALIBRATE") or line == "HOME":
            self._command_start = time.time()
            self._pending_done = True
            self._status_sent = False
        elif line == "PING":
            self._injected_lines.append("PONG")

    _injected_lines: list = []

    def _poll_lines(self):
        out = list(self._injected_lines)
        self._injected_lines.clear()
        if self._pending_done:
            elapsed = time.time() - self._command_start
            if elapsed > self.delay_sec * 0.3 and not self._status_sent:
                out.append("STATUS mock motion in progress")
                self._status_sent = True
            if elapsed > self.delay_sec:
                out.append("DONE")
                self._pending_done = False
        return out
