from __future__ import annotations

import re
import time
from typing import Any

from src.utils.exceptions import AlarmError, GRBLError

try:
    import serial
except ImportError:  # pragma: no cover - exercised only without optional dependency
    serial = None


MPOS_PATTERN = re.compile(r"MPos:([-0-9.]+),([-0-9.]+),([-0-9.]+)")


class GRBLClient:
    def __init__(self, timeout: float = 2.0):
        self.timeout = timeout
        self._serial: Any = None

    def connect(self, port: str, baudrate: int = 115200) -> None:
        if serial is None:
            raise GRBLError("pyserial is not installed")
        self._serial = serial.Serial(port, baudrate, timeout=self.timeout)
        time.sleep(2.0)
        self._serial.reset_input_buffer()

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def send_command(
        self,
        command: str,
        wait_ok: bool = True,
        timeout: float | None = None,
    ) -> list[str]:
        self._require_connection()
        line = command.strip()
        if not line:
            return []
        self._serial.write((line + "\n").encode("ascii"))
        if not wait_ok:
            return []
        return self._read_until_ok(timeout=timeout)

    def send_program(self, lines: list[str]) -> None:
        for line in lines:
            self.send_command(line, wait_ok=True)

    def get_status(self) -> dict[str, Any]:
        self._require_connection()
        self._serial.write(b"?")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            response = self._readline()
            if response.startswith("<"):
                return self._parse_status(response)
        raise GRBLError("Timed out waiting for GRBL status")

    def home(self) -> None:
        self.send_command("$H", timeout=90.0)

    def unlock(self) -> None:
        self.send_command("$X")

    def feed_hold(self) -> None:
        self._send_realtime(b"!")

    def resume(self) -> None:
        self._send_realtime(b"~")

    def reset(self) -> None:
        self._send_realtime(b"\x18")

    def _read_until_ok(self, timeout: float | None = None) -> list[str]:
        responses: list[str] = []
        deadline = time.monotonic() + (timeout if timeout is not None else self.timeout)
        while time.monotonic() < deadline:
            response = self._readline()
            if not response:
                continue
            responses.append(response)
            lower = response.lower()
            if lower == "ok":
                return responses
            if lower.startswith("error:"):
                raise GRBLError(response)
            if response.startswith("ALARM:"):
                raise AlarmError(response)
        raise GRBLError("Timed out waiting for GRBL ok")

    def _readline(self) -> str:
        raw = self._serial.readline()
        return raw.decode("ascii", errors="replace").strip()

    def _send_realtime(self, command: bytes) -> None:
        self._require_connection()
        self._serial.write(command)

    def _require_connection(self) -> None:
        if not self.is_connected():
            raise GRBLError("GRBL is not connected")

    @staticmethod
    def _parse_status(response: str) -> dict[str, Any]:
        state = response[1:].split("|", maxsplit=1)[0]
        match = MPOS_PATTERN.search(response)
        position = None
        if match:
            position = tuple(float(value) for value in match.groups())
        return {"raw": response, "state": state, "mpos": position}
