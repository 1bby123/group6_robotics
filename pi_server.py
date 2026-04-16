"""
Pi Server — Relay between Mac (TCP) and VEX EXP Brain (USB serial)
==================================================================
Runs on the Raspberry Pi. Accepts TCP connections from the Mac running
game.py and forwards commands to the VEX brain over USB, and forwards
the brain's responses back to the Mac.

Protocol on both sides is line-based ASCII, identical in both directions:
the Pi is a transparent relay and does not interpret commands.

Usage:
    pip install pyserial
    python3 pi_server.py [--port 9999] [--serial /dev/ttyACM0] [--baud 115200]

Find the brain's serial port:
    ls /dev/ttyACM*   (Linux/Pi)
    It's usually /dev/ttyACM0 when only the brain is plugged in.

Start this on the Pi *before* launching game.py on the Mac.
"""

import argparse
import socket
import sys
import threading
import time

try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed. Run: pip install pyserial")
    sys.exit(1)


class BrainSerial:
    """Thread-safe wrapper around the USB serial connection to the VEX brain."""

    def __init__(self, port, baud):
        self.port = port
        self.baud = baud
        self.ser = None
        self.lock = threading.Lock()
        self.connect()

    def connect(self):
        while True:
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
                print(f"[brain] connected on {self.port} @ {self.baud}")
                time.sleep(1)  # let brain settle
                self.ser.reset_input_buffer()
                return
            except serial.SerialException as e:
                print(f"[brain] connect failed: {e}  — retrying in 2s")
                time.sleep(2)

    def send(self, line):
        data = (line.rstrip("\n") + "\n").encode("ascii")
        with self.lock:
            try:
                self.ser.write(data)
                self.ser.flush()
            except serial.SerialException as e:
                print(f"[brain] write failed: {e}  — reconnecting")
                self.connect()

    def readline(self):
        """Non-blocking-ish line read. Returns '' if nothing available."""
        with self.lock:
            try:
                raw = self.ser.readline()
            except serial.SerialException as e:
                print(f"[brain] read failed: {e}  — reconnecting")
                self.connect()
                return ""
        if not raw:
            return ""
        try:
            return raw.decode("ascii", errors="replace").strip()
        except Exception:
            return ""


class ClientHandler:
    """Handles one TCP client connection, relaying to/from the brain."""

    def __init__(self, conn, addr, brain):
        self.conn = conn
        self.addr = addr
        self.brain = brain
        self.alive = True
        self.send_lock = threading.Lock()

    def send_to_client(self, line):
        if not self.alive:
            return
        try:
            with self.send_lock:
                self.conn.sendall((line.rstrip("\n") + "\n").encode("ascii"))
        except OSError:
            self.alive = False

    def run(self):
        print(f"[client {self.addr}] connected")

        # Pump brain → client in a background thread
        def pump_from_brain():
            while self.alive:
                line = self.brain.readline()
                if line:
                    print(f"[brain→mac] {line}")
                    self.send_to_client(line)
                else:
                    time.sleep(0.01)

        t = threading.Thread(target=pump_from_brain, daemon=True)
        t.start()

        # Pump client → brain in this thread
        buf = b""
        try:
            while self.alive:
                try:
                    chunk = self.conn.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("ascii", errors="replace").strip()
                    if text:
                        print(f"[mac→brain] {text}")
                        self.brain.send(text)
        finally:
            self.alive = False
            try:
                self.conn.close()
            except OSError:
                pass
            print(f"[client {self.addr}] disconnected")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9999,
                        help="TCP port to listen on (default 9999)")
    parser.add_argument("--serial", default="/dev/ttyACM0",
                        help="Serial port for VEX brain (default /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200,
                        help="Baud rate (default 115200)")
    args = parser.parse_args()

    brain = BrainSerial(args.serial, args.baud)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"[server] listening on 0.0.0.0:{args.port}")
    print(f"[server] find Pi IP with: hostname -I")

    try:
        while True:
            conn, addr = srv.accept()
            handler = ClientHandler(conn, addr, brain)
            handler.run()  # one client at a time — game.py is the only user
    except KeyboardInterrupt:
        print("\n[server] shutting down")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
