import pytest

from src.core.asrs_controller import ASRSController
from src.core.machine_config import MachineConfig
from src.db.database import Database
from src.db.models import Medicine
from src.utils.exceptions import GRBLError, SafetyError


class FakeGRBL:
    def __init__(self, fail_program: bool = False):
        self.connected = True
        self.fail_program = fail_program
        self.programs = []

    def connect(self, port, baudrate):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def is_connected(self):
        return self.connected

    def home(self):
        return None

    def send_program(self, lines):
        self.programs.append(lines)
        if self.fail_program:
            raise GRBLError("error: simulated failure")


def make_config(require_homing=True):
    return MachineConfig(
        z_high=-2.0,
        z_low=2.0,
        destination_x=9.5,
        destination_y=-2.9,
        home_x=0.0,
        home_y=0.0,
        feed_xy=600,
        feed_z=200,
        feed_home=300,
        require_homing_before_dispense=require_homing,
    )


def add_test_medicine(database):
    return database.add_medicine(
        Medicine(
            id=None,
            name="TestMed_A1",
            x=2.0,
            y=-9.1,
            stock=10,
            location_label="A1",
        )
    )


def test_controller_requires_homing_before_dispense(tmp_path):
    database = Database(tmp_path / "asrs.db")
    medicine_id = add_test_medicine(database)
    controller = ASRSController(make_config(), database, FakeGRBL())

    with pytest.raises(SafetyError):
        controller.distribute_medicine(medicine_id)


def test_controller_reduces_stock_after_success(tmp_path):
    database = Database(tmp_path / "asrs.db")
    medicine_id = add_test_medicine(database)
    controller = ASRSController(make_config(), database, FakeGRBL())
    controller.home()

    program = controller.distribute_medicine(medicine_id)

    assert program[3] == "G1 X2.000 Y-9.100 F600"
    assert database.get_medicine(medicine_id).stock == 9


def test_controller_keeps_stock_when_grbl_fails(tmp_path):
    database = Database(tmp_path / "asrs.db")
    medicine_id = add_test_medicine(database)
    controller = ASRSController(make_config(), database, FakeGRBL(fail_program=True))
    controller.home()

    with pytest.raises(GRBLError):
        controller.distribute_medicine(medicine_id)

    assert database.get_medicine(medicine_id).stock == 10

