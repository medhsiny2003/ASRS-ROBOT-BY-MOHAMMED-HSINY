from __future__ import annotations

from src.core.gcode_generator import GCodeGenerator
from src.core.grbl_client import GRBLClient
from src.core.machine_config import MachineConfig
from src.core.state_machine import MachineState
from src.db.database import Database
from src.utils.exceptions import ASRSError, GRBLError, SafetyError


class ASRSController:
    def __init__(
        self,
        config: MachineConfig,
        database: Database,
        grbl: GRBLClient | None = None,
    ):
        self.config = config
        self.database = database
        self.grbl = grbl or GRBLClient()
        self.generator = GCodeGenerator(config)
        self.state = MachineState.DISCONNECTED
        self.is_homed = False

    def connect_machine(self, port: str) -> None:
        self.grbl.connect(port, self.config.baudrate)
        self.state = MachineState.CONNECTED
        self.database.log_machine_event("connect", f"Connected to {port}")

    def disconnect_machine(self) -> None:
        self.grbl.disconnect()
        self.state = MachineState.DISCONNECTED
        self.is_homed = False
        self.database.log_machine_event("disconnect", "Disconnected")

    def home(self) -> None:
        self._require_connected()
        self.state = MachineState.HOMING
        self.grbl.home()
        self.state = MachineState.READY
        self.is_homed = True
        self.database.log_machine_event("home", "Homing completed")

    def distribute_medicine(self, medicine_id: int) -> list[str]:
        self._require_ready_for_dispense()
        medicine = self.database.get_medicine(medicine_id)
        if medicine is None:
            raise SafetyError(f"Medicine {medicine_id} was not found")
        if medicine.stock <= 0:
            self.database.log_dispense(medicine, "FAILED", "Out of stock")
            raise SafetyError(f"{medicine.name} is out of stock")

        try:
            program = self.generator.generate_dispense_cycle(medicine.x, medicine.y)
            self.state = MachineState.MOVING_TO_MEDICINE
            self.grbl.send_program(program)
            self.database.reduce_stock(medicine_id)
            self.database.log_dispense(medicine, "SUCCESS", "Dispense cycle completed")
            self.state = MachineState.READY
            return program
        except Exception as exc:
            self.state = MachineState.ERROR
            self.database.log_dispense(medicine, "FAILED", str(exc))
            if isinstance(exc, ASRSError):
                raise
            raise ASRSError(str(exc)) from exc

    def preview_dispense(self, medicine_id: int) -> list[str]:
        medicine = self.database.get_medicine(medicine_id)
        if medicine is None:
            raise SafetyError(f"Medicine {medicine_id} was not found")
        return self.generator.generate_dispense_cycle(medicine.x, medicine.y)

    def reset_alarm(self) -> None:
        self._require_connected()
        self.grbl.unlock()
        self.state = MachineState.READY if self.is_homed else MachineState.CONNECTED
        self.database.log_machine_event("unlock", "Alarm reset requested")

    def stop(self) -> None:
        self._require_connected()
        self.grbl.feed_hold()
        self.state = MachineState.STOPPED
        self.database.log_machine_event("feed_hold", "Feed hold sent")

    def resume(self) -> None:
        self._require_connected()
        self.grbl.resume()
        self.database.log_machine_event("resume", "Cycle start sent")

    def soft_reset(self) -> None:
        self._require_connected()
        self.grbl.reset()
        self.state = MachineState.CONNECTED
        self.is_homed = False
        self.database.log_machine_event("soft_reset", "Soft reset sent")

    def get_position(self) -> tuple[float, float, float]:
        status = self.grbl.get_status()
        if status.get("mpos") is None:
            raise GRBLError("GRBL status did not include MPos")
        return status["mpos"]

    def _require_connected(self) -> None:
        if not self.grbl.is_connected():
            raise SafetyError("Machine is not connected")

    def _require_ready_for_dispense(self) -> None:
        self._require_connected()
        if self.config.require_homing_before_dispense and not self.is_homed:
            raise SafetyError("Machine must be homed before dispensing")
        if self.state in {MachineState.ALARM, MachineState.ERROR, MachineState.STOPPED}:
            raise SafetyError(f"Machine is not ready: {self.state}")

