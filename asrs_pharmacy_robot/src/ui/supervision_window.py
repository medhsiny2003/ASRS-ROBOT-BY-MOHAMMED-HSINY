from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.asrs_controller import ASRSController
from src.core.machine_config import MachineConfig
from src.core.state_machine import MachineState
from src.db.database import Database
from src.db.models import Medicine
from src.utils.logger import configure_logging

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    list_ports = None


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_DIR / "config" / "machine_config.json"
DEFAULT_DB = PROJECT_DIR / "data" / "asrs.db"
LOGO_PATH = PROJECT_DIR / "assets" / "moratek_logo.png"
PHARMACY_LOGO_PATH = PROJECT_DIR / "assets" / "pharmacists_morocco_logo.png"
FACULTY_LOGO_PATH = PROJECT_DIR / "assets" / "fst_logo.png"


class TaskWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, task: Callable[[], Any]):
        super().__init__()
        self.task = task

    def run(self) -> None:
        try:
            self.finished.emit(self.task())
        except Exception as exc:  # pragma: no cover
            self.failed.emit(str(exc))


class MedicineDialog(QDialog):
    def __init__(self, parent: QWidget, medicine: Medicine | None = None):
        super().__init__(parent)
        self.setWindowTitle("Fiche medicament")
        self.setMinimumWidth(420)
        self._id = medicine.id if medicine else None
        self.name = QLineEdit(medicine.name if medicine else "")
        self.location = QLineEdit(medicine.location_label or "" if medicine else "")
        self.category = QLineEdit(medicine.category or "" if medicine else "")
        self.expiry = QLineEdit(medicine.expiry_date or "" if medicine else "")
        self.x = QDoubleSpinBox()
        self.y = QDoubleSpinBox()
        for spin in (self.x, self.y):
            spin.setRange(-1000.0, 1000.0)
            spin.setDecimals(3)
        self.x.setValue(medicine.x if medicine else 0.0)
        self.y.setValue(medicine.y if medicine else 0.0)
        self.stock = QSpinBox()
        self.stock.setRange(0, 100000)
        self.stock.setValue(medicine.stock if medicine else 0)

        form = QFormLayout()
        form.addRow("Nom", self.name)
        form.addRow("Coordonnee X", self.x)
        form.addRow("Coordonnee Y", self.y)
        form.addRow("Stock", self.stock)
        form.addRow("Case / bac", self.location)
        form.addRow("Categorie", self.category)
        form.addRow("Expiration", self.expiry)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def medicine(self) -> Medicine:
        name = self.name.text().strip()
        if not name:
            raise ValueError("Le nom du medicament est obligatoire")
        return Medicine(
            id=self._id,
            name=name,
            x=self.x.value(),
            y=self.y.value(),
            stock=self.stock.value(),
            location_label=self.location.text().strip() or None,
            category=self.category.text().strip() or None,
            expiry_date=self.expiry.text().strip() or None,
        )


class SupervisionWindow(QMainWindow):
    def __init__(self, config_path: Path = DEFAULT_CONFIG, db_path: Path = DEFAULT_DB):
        super().__init__()
        self.setWindowTitle("MORATEK SkyPharma")
        self.resize(1320, 820)
        self.config = MachineConfig.from_json(config_path)
        self.database = Database(db_path)
        self.controller = ASRSController(self.config, self.database)
        self.selected: Medicine | None = None
        self.thread: QThread | None = None
        self.worker: TaskWorker | None = None
        self.current_job = "Aucune livraison"
        self.current_position: tuple[float, float, float] | None = None
        self._build_ui()
        self.position_timer = QTimer(self)
        self.position_timer.setInterval(1500)
        self.position_timer.timeout.connect(self.poll_position)
        self.refresh_ports()
        self.refresh_medicines()
        self.refresh_logs()
        self.update_state()

    def _build_ui(self) -> None:
        self.setStatusBar(QStatusBar(self))
        root = QWidget()
        self.setCentralWidget(root)
        page = QVBoxLayout(root)
        page.setContentsMargins(18, 14, 18, 14)
        page.setSpacing(12)
        page.addWidget(self._header())
        page.addWidget(self._status_panel())
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._order_panel())
        split.addWidget(self._tabs())
        split.setSizes([570, 730])
        page.addWidget(split, 1)
        self.setStyleSheet(self._css())

    def _header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Header")
        row = QHBoxLayout(frame)
        row.setContentsMargins(18, 12, 18, 12)
        logo = QLabel()
        logo.setFixedSize(QSize(180, 70))
        if LOGO_PATH.exists():
            logo.setPixmap(
                QPixmap(str(LOGO_PATH)).scaled(
                    logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        title = QVBoxLayout()
        h1 = QLabel("SkyPharma")
        h1.setObjectName("Title")
        sub = QLabel("Supervision pharmacie | Poste local robot")
        sub.setObjectName("Subtitle")
        title.addWidget(h1)
        title.addWidget(sub)
        self.emergency = QPushButton("ARRET D'URGENCE")
        self.emergency.setObjectName("Emergency")
        self.emergency.setMinimumSize(220, 58)
        self.emergency.clicked.connect(self.emergency_stop)
        self.resume = QPushButton("Reprendre cycle ~")
        self.resume.clicked.connect(lambda: self.run_task("Reprise", self.controller.resume))
        emergency_box = QVBoxLayout()
        emergency_box.addWidget(self.emergency)
        emergency_box.addWidget(self.resume)
        row.addWidget(logo)
        row.addLayout(title)
        row.addStretch(1)
        row.addWidget(self._faculty_logo())
        row.addWidget(self._pharmacy_logo())
        row.addLayout(emergency_box)
        return frame

    def _faculty_logo(self) -> QLabel:
        logo = QLabel("FST")
        logo.setObjectName("FacultyLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(QSize(230, 70))
        if FACULTY_LOGO_PATH.exists():
            logo.setText("")
            logo.setPixmap(
                QPixmap(str(FACULTY_LOGO_PATH)).scaled(
                    logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return logo

    def _pharmacy_logo(self) -> QLabel:
        logo = QLabel("Logo\nPharmaciens\nMaroc")
        logo.setObjectName("PartnerLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(QSize(110, 70))
        if PHARMACY_LOGO_PATH.exists():
            logo.setText("")
            logo.setPixmap(
                QPixmap(str(PHARMACY_LOGO_PATH)).scaled(
                    logo.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return logo

    def _status_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("StatusPanel")
        row = QHBoxLayout(panel)
        row.setContentsMargins(12, 10, 12, 10)
        self.station_card = self._card("Etat machine", "Non connecte")
        self.conn_card = self._card("Connexion", "Deconnecte")
        self.job_card = self._card("Livraison", self.current_job)
        self.stock_card = self._card("Stock", "-")
        row.addWidget(self.station_card)
        row.addWidget(self.conn_card)
        row.addWidget(self.job_card)
        row.addWidget(self.stock_card)
        return panel

    def _card(self, title: str, value: str) -> QLabel:
        label = QLabel(f"<span>{title}</span><br><strong>{value}</strong>")
        label.setObjectName("Card")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setMinimumHeight(72)
        return label

    def _order_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        box = QVBoxLayout(panel)
        box.setContentsMargins(16, 16, 16, 16)
        head = QLabel("Medicaments et stock")
        head.setObjectName("Section")
        box.addWidget(head)
        search = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un medicament, ID ou case")
        self.search.textChanged.connect(self.refresh_medicines)
        seed = QPushButton("Test A1")
        seed.clicked.connect(self.seed_test_medicine)
        search.addWidget(self.search, 1)
        search.addWidget(seed)
        box.addLayout(search)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "Nom", "X", "Y", "Stock", "Case", "Expiration"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.on_selected)
        self.table.doubleClicked.connect(self.edit_medicine)
        box.addWidget(self.table, 1)
        self.selected_label = QLabel("Fiche selectionnee: aucun medicament")
        self.selected_label.setObjectName("Info")
        box.addWidget(self.selected_label)
        actions = QGridLayout()
        self.dispense = QPushButton("Lancer livraison")
        self.dispense.setObjectName("Primary")
        self.preview = QPushButton("G-code")
        add = QPushButton("Ajouter")
        edit = QPushButton("Modifier")
        delete = QPushButton("Desactiver")
        self.dispense.clicked.connect(self.confirm_dispense)
        self.preview.clicked.connect(self.preview_gcode)
        add.clicked.connect(self.add_medicine)
        edit.clicked.connect(self.edit_medicine)
        delete.clicked.connect(self.deactivate_medicine)
        actions.addWidget(self.dispense, 0, 0, 1, 2)
        actions.addWidget(self.preview, 0, 2)
        actions.addWidget(add, 1, 0)
        actions.addWidget(edit, 1, 1)
        actions.addWidget(delete, 1, 2)
        box.addLayout(actions)
        return panel

    def _tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.addTab(self._supervision_tab(), "Connexion et tests")
        tabs.addTab(self._jog_tab(), "Jog / Coordonnees")
        tabs.addTab(self._history_tab(), "Historique")
        tabs.addTab(self._tech_tab(), "Maintenance")
        return tabs

    def _supervision_tab(self) -> QWidget:
        tab = QWidget()
        box = QVBoxLayout(tab)
        box.setContentsMargins(10, 10, 10, 10)
        box.setSpacing(10)
        machine = QGroupBox("Connexion robot")
        grid = QGridLayout(machine)
        grid.setContentsMargins(10, 16, 10, 10)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.port = QComboBox()
        refresh = QPushButton("Actualiser")
        self.connect = QPushButton("Connecter")
        self.disconnect = QPushButton("Deconnecter")
        self.home = QPushButton("Homing $H")
        self.unlock = QPushButton("Reset alarme $X")
        self.soft_reset = QPushButton("Soft reset")
        self.read_pos = QPushButton("Lire position")
        self.conn_label = QLabel("Deconnecte")
        self.grbl_label = QLabel("-")
        refresh.clicked.connect(self.refresh_ports)
        self.connect.clicked.connect(self.connect_machine)
        self.disconnect.clicked.connect(self.disconnect_machine)
        self.home.clicked.connect(lambda: self.run_task("Homing", self.controller.home))
        self.unlock.clicked.connect(lambda: self.run_task("Reset alarme", self.controller.reset_alarm))
        self.soft_reset.clicked.connect(lambda: self.run_task("Soft reset", self.controller.soft_reset))
        self.read_pos.clicked.connect(self.read_position)
        grid.addWidget(QLabel("Port COM"), 0, 0)
        grid.addWidget(self.port, 0, 1)
        grid.addWidget(refresh, 0, 2)
        grid.addWidget(self.connect, 1, 0)
        grid.addWidget(self.disconnect, 1, 1)
        grid.addWidget(self.read_pos, 1, 2)
        grid.addWidget(self.home, 2, 0)
        grid.addWidget(self.unlock, 2, 1)
        grid.addWidget(self.soft_reset, 2, 2)
        box.addWidget(machine)
        cycle = QFrame()
        cycle.setObjectName("DeliveryPanel")
        flow = QVBoxLayout(cycle)
        flow.setContentsMargins(10, 8, 10, 10)
        flow.setSpacing(6)
        delivery_title = QLabel("Suivi livraison")
        delivery_title.setObjectName("DeliveryTitle")
        self.delivery_state = QLabel("Pret")
        self.delivery_state.setObjectName("DeliveryState")
        self.delivery_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.delivery_state.setMinimumHeight(42)
        flow.addWidget(delivery_title)
        flow.addWidget(self.delivery_state)
        box.addWidget(cycle)
        self.alert = QLabel("Aucune alerte")
        self.alert.setObjectName("AlertOk")
        self.alert.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alert.setMinimumHeight(34)
        box.addWidget(self.alert)
        box.addStretch(1)
        return tab

    def _jog_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)
        layout.addWidget(self._position_group(), 1)
        layout.addWidget(self._jog_group(), 1)
        return tab

    def _position_group(self) -> QGroupBox:
        group = QGroupBox("Coordonnees absolues GRBL")
        box = QVBoxLayout(group)
        box.setContentsMargins(12, 18, 12, 12)
        self.x_readout = self._axis_readout("X", "0.000")
        self.y_readout = self._axis_readout("Y", "0.000")
        self.z_readout = self._axis_readout("Z", "0.000")
        box.addWidget(self.x_readout)
        box.addWidget(self.y_readout)
        box.addWidget(self.z_readout)
        self.add_from_position = QPushButton("Ajouter fiche depuis position")
        self.add_from_position.clicked.connect(self.add_medicine_from_position)
        box.addWidget(self.add_from_position)
        box.addStretch(1)
        return group

    def _axis_readout(self, axis: str, value: str) -> QLabel:
        label = QLabel(f"{axis}      {value}")
        label.setObjectName("AxisReadout")
        label.setMinimumHeight(54)
        return label

    def _jog_group(self) -> QGroupBox:
        group = QGroupBox("Jog control")
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 18, 12, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.step = QDoubleSpinBox()
        self.step.setRange(0.1, 100.0)
        self.step.setDecimals(2)
        self.step.setValue(1.0)
        self.jog_feed = QSpinBox()
        self.jog_feed.setRange(50, 2000)
        self.jog_feed.setValue(self.config.feed_xy)
        self.y_plus = QPushButton("Y+")
        self.y_minus = QPushButton("Y-")
        self.x_minus = QPushButton("X-")
        self.x_plus = QPushButton("X+")
        self.xy_up_left = QPushButton("X- Y+")
        self.xy_up_right = QPushButton("X+ Y+")
        self.xy_down_left = QPushButton("X- Y-")
        self.xy_down_right = QPushButton("X+ Y-")
        self.z_plus = QPushButton("Z+")
        self.z_minus = QPushButton("Z-")
        self.y_plus.clicked.connect(lambda: self.jog("Y", self.step.value()))
        self.y_minus.clicked.connect(lambda: self.jog("Y", -self.step.value()))
        self.x_plus.clicked.connect(lambda: self.jog("X", self.step.value()))
        self.x_minus.clicked.connect(lambda: self.jog("X", -self.step.value()))
        self.xy_up_left.clicked.connect(lambda: self.jog_xy(-self.step.value(), self.step.value()))
        self.xy_up_right.clicked.connect(lambda: self.jog_xy(self.step.value(), self.step.value()))
        self.xy_down_left.clicked.connect(lambda: self.jog_xy(-self.step.value(), -self.step.value()))
        self.xy_down_right.clicked.connect(lambda: self.jog_xy(self.step.value(), -self.step.value()))
        self.z_plus.clicked.connect(lambda: self.jog("Z", self.step.value()))
        self.z_minus.clicked.connect(lambda: self.jog("Z", -self.step.value()))
        for button in [
            self.y_plus,
            self.y_minus,
            self.x_minus,
            self.x_plus,
            self.xy_up_left,
            self.xy_up_right,
            self.xy_down_left,
            self.xy_down_right,
            self.z_plus,
            self.z_minus,
        ]:
            self._style_jog_button(button)
        grid.addWidget(QLabel("Pas XY/Z"), 0, 0)
        grid.addWidget(self.step, 0, 1)
        grid.addWidget(QLabel("Feed"), 1, 0)
        grid.addWidget(self.jog_feed, 1, 1)
        grid.addWidget(self.xy_up_left, 2, 0)
        grid.addWidget(self.y_plus, 2, 1)
        grid.addWidget(self.xy_up_right, 2, 2)
        grid.addWidget(self.x_minus, 3, 0)
        grid.addWidget(self.x_plus, 3, 2)
        grid.addWidget(self.xy_down_left, 4, 0)
        grid.addWidget(self.y_minus, 4, 1)
        grid.addWidget(self.xy_down_right, 4, 2)
        grid.addWidget(self.z_plus, 2, 3)
        grid.addWidget(self.z_minus, 4, 3)
        return group

    def _style_jog_button(self, button: QPushButton) -> None:
        button.setObjectName("JogButton")
        button.setMinimumSize(76, 42)

    def _history_tab(self) -> QWidget:
        tab = QWidget()
        box = QVBoxLayout(tab)
        self.history = QTableWidget(0, 7)
        self.history.setHorizontalHeaderLabels(["Date", "ID", "Medicament", "X", "Y", "Resultat", "Message"])
        self.events = QTableWidget(0, 4)
        self.events.setHorizontalHeaderLabels(["Date", "Evenement", "Message", "Etat GRBL"])
        for table in (self.history, self.events):
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            table.verticalHeader().setVisible(False)
            box.addWidget(table, 1)
        return tab

    def _tech_tab(self) -> QWidget:
        tab = QWidget()
        box = QVBoxLayout(tab)
        info = QLabel(
            "Maintenance: le G-code n'est pas stocke complet dans la base. "
            "Il est genere depuis les coordonnees X/Y du medicament et machine_config.json."
        )
        info.setWordWrap(True)
        info.setObjectName("Info")
        self.gcode = QTextEdit()
        self.gcode.setReadOnly(True)
        self.gcode.setPlaceholderText("Selectionner un medicament puis cliquer sur G-code")
        box.addWidget(info)
        box.addWidget(self.gcode, 1)
        return tab

    def refresh_ports(self) -> None:
        current = self.port.currentText()
        self.port.clear()
        ports = [p.device for p in list_ports.comports()] if list_ports else []
        self.port.addItems(ports or ["COM5"])
        if current and (index := self.port.findText(current)) >= 0:
            self.port.setCurrentIndex(index)

    def connect_machine(self) -> None:
        port = self.port.currentText().strip()
        if not port:
            self.show_error("Choisis un port COM")
            return
        self.run_task(f"Connexion {port}", lambda: self.controller.connect_machine(port))

    def disconnect_machine(self) -> None:
        self.controller.disconnect_machine()
        self.current_job = "Aucune livraison"
        self.current_position = None
        self.update_state()
        self.refresh_logs()

    def emergency_stop(self) -> None:
        try:
            self.controller.stop()
            self.current_job = "Arret urgence"
            self.update_state()
            self.refresh_logs()
        except Exception as exc:
            self.show_error(str(exc))

    def read_position(self) -> None:
        def done(pos: tuple[float, float, float]) -> None:
            self.update_position_display(pos)

        self.run_task("Lecture position", self.controller.get_position, done)

    def poll_position(self) -> None:
        if self.thread is not None or not self.controller.grbl.is_connected():
            return
        self.run_task("Position", self.controller.get_position, self.update_position_display)

    def update_position_display(self, pos: tuple[float, float, float]) -> None:
        self.current_position = pos
        self.x_readout.setText(f"X      {pos[0]:.3f}")
        self.y_readout.setText(f"Y      {pos[1]:.3f}")
        self.z_readout.setText(f"Z      {pos[2]:.3f}")

    def jog(self, axis: str, distance: float) -> None:
        if not self.controller.grbl.is_connected():
            self.show_error("Connecter le robot avant jog")
            return
        if not self.controller.is_homed:
            self.show_error("Faire homing avant jog manuel")
            return
        feed = self.jog_feed.value()
        command = f"$J=G91 G21 {axis}{distance:.3f} F{feed}"
        def move_and_read() -> tuple[float, float, float]:
            self.controller.grbl.send_command(command)
            return self.controller.get_position()

        self.run_task(f"Jog {axis}", move_and_read, self.update_position_display)

    def jog_xy(self, x_distance: float, y_distance: float) -> None:
        if not self.controller.grbl.is_connected():
            self.show_error("Connecter le robot avant jog")
            return
        if not self.controller.is_homed:
            self.show_error("Faire homing avant jog manuel")
            return
        feed = self.jog_feed.value()
        command = f"$J=G91 G21 X{x_distance:.3f} Y{y_distance:.3f} F{feed}"

        def move_and_read() -> tuple[float, float, float]:
            self.controller.grbl.send_command(command)
            return self.controller.get_position()

        self.run_task("Jog XY", move_and_read, self.update_position_display)

    def add_medicine_from_position(self) -> None:
        if self.current_position is None:
            self.show_error("Lire la position X/Y/Z avant ajout")
            return
        x, y, _z = self.current_position
        dialog = MedicineDialog(
            self,
            Medicine(
                id=None,
                name="",
                x=x,
                y=y,
                stock=0,
                location_label="",
            ),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.database.add_medicine(dialog.medicine())
            self.refresh_medicines()

    def refresh_medicines(self) -> None:
        medicines = self.database.search_medicines(self.search.text().strip() if hasattr(self, "search") else "")
        all_medicines = self.database.search_medicines("")
        out_count = sum(1 for med in all_medicines if med.stock <= 0)
        self.stock_card.setText(
            f"<span>Stock</span><br><strong>{len(all_medicines)} refs | {out_count} rupture</strong>"
        )
        self.table.setRowCount(len(medicines))
        for row, med in enumerate(medicines):
            values = [med.id, med.name, f"{med.x:.3f}", f"{med.y:.3f}", "RUPTURE" if med.stock <= 0 else med.stock, med.location_label or "", med.expiry_date or ""]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, med)
                self.table.setItem(row, col, item)
        self.on_selected()

    def on_selected(self) -> None:
        items = self.table.selectedItems()
        self.selected = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        if not self.selected:
            self.selected_label.setText("Fiche selectionnee: aucun medicament")
            return
        med = self.selected
        self.selected_label.setText(f"Fiche selectionnee: {med.name} | Case {med.location_label or '-'} | Stock {med.stock} | X {med.x:.3f} Y {med.y:.3f}")

    def add_medicine(self) -> None:
        dialog = MedicineDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.database.add_medicine(dialog.medicine())
            self.refresh_medicines()

    def edit_medicine(self) -> None:
        if not self.selected:
            self.show_error("Selectionner un medicament")
            return
        dialog = MedicineDialog(self, self.selected)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.database.update_medicine(dialog.medicine())
            self.refresh_medicines()

    def deactivate_medicine(self) -> None:
        if not self.selected or self.selected.id is None:
            self.show_error("Selectionner un medicament")
            return
        if QMessageBox.question(self, "Desactiver", f"Desactiver {self.selected.name} ?") == QMessageBox.StandardButton.Yes:
            self.database.deactivate_medicine(self.selected.id)
            self.refresh_medicines()

    def seed_test_medicine(self) -> None:
        med_id = self.database.seed_test_medicine()
        self.refresh_medicines()
        self.statusBar().showMessage(f"TestMed_A1 pret avec ID {med_id}")

    def preview_gcode(self) -> None:
        if not self.selected or self.selected.id is None:
            self.show_error("Selectionner un medicament")
            return
        self.gcode.setPlainText("\n".join(self.controller.preview_dispense(self.selected.id)))

    def confirm_dispense(self) -> None:
        if not self.selected or self.selected.id is None:
            self.show_error("Selectionner un medicament")
            return
        self.preview_gcode()
        if QMessageBox.question(self, "Validation livraison", f"Lancer un cycle de validation pour {self.selected.name} ?") != QMessageBox.StandardButton.Yes:
            return
        med_id = self.selected.id
        self.current_job = self.selected.name
        self.update_state()
        self.run_task("Livraison", lambda: self.controller.distribute_medicine(med_id), lambda program: self.gcode.setPlainText("\n".join(program)))

    def refresh_logs(self) -> None:
        rows = list(self.database.dispense_history())
        self.history.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [row["created_at"], row["medicine_id"] or "", row["medicine_name"] or "", "" if row["x"] is None else f"{row['x']:.3f}", "" if row["y"] is None else f"{row['y']:.3f}", row["status"], row["message"] or ""]
            for c, value in enumerate(values):
                self.history.setItem(r, c, QTableWidgetItem(str(value)))
        rows = list(self.database.machine_events())
        self.events.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate([row["created_at"], row["event_type"], row["message"] or "", row["grbl_state"] or ""]):
                self.events.setItem(r, c, QTableWidgetItem(str(value)))

    def run_task(self, label: str, task: Callable[[], Any], on_success: Callable[[Any], None] | None = None) -> None:
        if self.thread is not None:
            self.show_error("Une commande machine est deja en cours")
            return
        self.set_busy(True, label)
        self.thread = QThread(self)
        self.worker = TaskWorker(task)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(lambda result: self._task_finished(label, result, on_success))
        self.worker.failed.connect(lambda msg: self._task_failed(label, msg))
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.start()

    def _task_finished(self, label: str, result: Any, on_success: Callable[[Any], None] | None) -> None:
        if on_success:
            on_success(result)
        if label == "Position":
            self.set_busy(False, label)
            self.update_state()
            return
        if label == "Livraison":
            self.current_job = "Aucune livraison"
        self.set_busy(False, label)
        self.update_state()
        self.refresh_medicines()
        self.refresh_logs()

    def _task_failed(self, label: str, message: str) -> None:
        if label == "Position":
            self.set_busy(False, label)
            return
        if label == "Livraison":
            self.current_job = "Echec livraison"
        self.set_busy(False, label)
        self.update_state()
        self.refresh_logs()
        self.show_error(f"{label}: {message}")

    def _cleanup_thread(self) -> None:
        self.thread = None
        self.worker = None

    def set_busy(self, busy: bool, label: str) -> None:
        if label == "Position":
            return
        for button in [self.connect, self.disconnect, self.home, self.unlock, self.soft_reset, self.read_pos, self.dispense, self.preview]:
            button.setEnabled(not busy)
        for button in self._jog_buttons():
            button.setEnabled(not busy and self.controller.grbl.is_connected())
        self.emergency.setEnabled(self.controller.grbl.is_connected())
        if busy and label == "Livraison":
            self._set_step("moving")
        self.statusBar().showMessage(f"{label} en cours..." if busy else "Pret")

    def update_state(self) -> None:
        connected = self.controller.grbl.is_connected()
        state = self.controller.state
        station, kind = self._station_status(state, connected)
        self.conn_label.setText("Connecte" if connected else "Deconnecte")
        self.grbl_label.setText(str(state))
        self.station_card.setProperty("kind", kind)
        self.station_card.setText(f"<span>Etat machine</span><br><strong>{station}</strong>")
        self.station_card.style().unpolish(self.station_card)
        self.station_card.style().polish(self.station_card)
        self.conn_card.setText(f"<span>Connexion</span><br><strong>{'Connecte' if connected else 'Deconnecte'}</strong>")
        self.job_card.setText(f"<span>Livraison</span><br><strong>{self.current_job}</strong>")
        self.alert.setText(self._alert_text(state, connected))
        self.alert.setObjectName("AlertBad" if state in {MachineState.ERROR, MachineState.ALARM, MachineState.STOPPED} else "AlertOk")
        self.alert.style().unpolish(self.alert)
        self.alert.style().polish(self.alert)
        for button in [self.disconnect, self.home, self.unlock, self.emergency, self.resume, self.soft_reset, self.read_pos]:
            button.setEnabled(connected)
        for button in self._jog_buttons():
            button.setEnabled(connected)
        if connected and not self.position_timer.isActive():
            self.position_timer.start()
        if not connected and self.position_timer.isActive():
            self.position_timer.stop()
        self._set_step(self._step_for_state(state, connected))

    def _station_status(self, state: MachineState, connected: bool) -> tuple[str, str]:
        if not connected:
            return "HORS LIGNE", "neutral"
        if state in {MachineState.ERROR, MachineState.ALARM, MachineState.STOPPED}:
            return ("ARRET ACTIVE" if state == MachineState.STOPPED else "ALARME", "danger")
        moving = {MachineState.HOMING, MachineState.MOVING_TO_MEDICINE, MachineState.Z_DOWN_PICK, MachineState.Z_UP_PICK, MachineState.MOVING_TO_DESTINATION, MachineState.Z_DOWN_DROP, MachineState.Z_UP_DROP, MachineState.RETURNING_HOME}
        if state in moving:
            return "CYCLE EN COURS", "busy"
        if self.controller.is_homed or state == MachineState.READY:
            return "DISPONIBLE", "ready"
        return "REFERENCEMENT REQUIS", "busy"

    def _alert_text(self, state: MachineState, connected: bool) -> str:
        if not connected:
            return "HORS LIGNE"
        if state in {MachineState.ERROR, MachineState.ALARM}:
            return "ALARME"
        if state == MachineState.STOPPED:
            return "ARRET ACTIVE"
        if not self.controller.is_homed:
            return "HOMING REQUIS"
        return "PRET"

    def _step_for_state(self, state: MachineState, connected: bool) -> str:
        if not connected:
            return ""
        if state in {MachineState.READY, MachineState.CONNECTED}:
            return "ready"
        if state in {MachineState.MOVING_TO_MEDICINE, MachineState.MOVING_TO_DESTINATION}:
            return "moving"
        if state in {MachineState.Z_DOWN_PICK, MachineState.Z_UP_PICK}:
            return "pick"
        if state in {MachineState.Z_DOWN_DROP, MachineState.Z_UP_DROP}:
            return "drop"
        if state == MachineState.RETURNING_HOME:
            return "return"
        if state == MachineState.DONE:
            return "done"
        return ""

    def _set_step(self, active: str) -> None:
        names = {
            "ready": "Pret",
            "moving": "Deplacement en cours",
            "pick": "Prise medicament",
            "drop": "Depot medicament",
            "return": "Retour home",
            "done": "Cycle termine",
            "": "En attente",
        }
        self.delivery_state.setText(names.get(active, "En attente"))
        self.delivery_state.setObjectName("StepActive" if active else "StepIdle")
        self.delivery_state.style().unpolish(self.delivery_state)
        self.delivery_state.style().polish(self.delivery_state)

    def _jog_buttons(self) -> list[QPushButton]:
        return [
            self.y_plus,
            self.y_minus,
            self.x_minus,
            self.x_plus,
            self.xy_up_left,
            self.xy_up_right,
            self.xy_down_left,
            self.xy_down_right,
            self.z_plus,
            self.z_minus,
            self.add_from_position,
        ]

    def show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Erreur", message)
        self.statusBar().showMessage(message)

    def _css(self) -> str:
        return """
        QWidget { background: #eef2f6; color: #172033; font-family: Segoe UI, Arial; font-size: 13px; }
        QLabel { background: transparent; }
        QFrame#Header, QFrame#Panel, QFrame#StatusPanel, QGroupBox {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
        }
        QLabel#Title { font-size: 26px; font-weight: 800; color: #0f2a4d; }
        QLabel#Subtitle { font-size: 14px; color: #526173; }
        QLabel#Section { font-size: 18px; font-weight: 800; color: #0f2a4d; }
        QLabel#PartnerLogo, QLabel#FacultyLogo {
            background: transparent;
            border: 0;
            border-radius: 4px;
            color: #64748b;
            font-size: 11px;
            font-weight: 700;
        }
        QFrame#DeliveryPanel {
            background: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
        }
        QLabel#DeliveryTitle {
            color: #0f2a4d;
            font-weight: 800;
            font-size: 13px;
            padding: 0;
        }
        QLabel#Card {
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-left: 4px solid #64748b;
            border-radius: 4px;
            padding: 10px 14px;
        }
        QLabel#Card span { color: #64748b; }
        QLabel#Card strong { font-size: 17px; color: #0f172a; }
        QLabel#Card[kind="ready"] strong { color: #087443; }
        QLabel#Card[kind="busy"] strong { color: #a15c00; }
        QLabel#Card[kind="danger"] strong { color: #b42318; }
        QLabel#SmallTitle { color: #526173; font-weight: 800; }
        QLabel#Info { background: transparent; border: 0; padding: 6px 0; color: #173b73; }
        QFrame#PositionPanel { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; }
        QPushButton {
            background: #ffffff;
            border: 1px solid #b8c2d0;
            border-radius: 4px;
            padding: 8px 12px;
            min-height: 30px;
            color: #172033;
            font-weight: 700;
        }
        QPushButton:hover { background: #eef6ff; border-color: #6b93c9; }
        QPushButton:disabled { background: #f1f5f9; color: #94a3b8; border-color: #d8e0ea; }
        QPushButton#Primary { background: #0f766e; color: white; font-size: 15px; font-weight: 800; min-height: 42px; }
        QPushButton#Primary:hover { background: #0d9488; }
        QPushButton#Emergency { background: #c91f1f; color: white; border: 2px solid #8f1111; font-size: 16px; font-weight: 900; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
            background: #ffffff;
            border: 1px solid #b8c2d0;
            border-radius: 4px;
            padding: 7px;
            color: #172033;
        }
        QTableWidget {
            background: #ffffff;
            color: #172033;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            gridline-color: #e2e8f0;
            selection-background-color: #cfe1ff;
        }
        QHeaderView::section {
            background: #e7edf5;
            color: #172033;
            border: 0;
            padding: 8px;
            font-weight: 800;
        }
        QLabel#StepIdle { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; color: #526173; font-weight: 700; }
        QLabel#StepActive { background: #dff7ed; border: 1px solid #5abf90; border-radius: 4px; color: #046c4e; font-weight: 900; }
        QLabel#DeliveryState { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; color: #526173; font-weight: 700; }
        QLabel#AxisReadout {
            background: #ffffff;
            border: 2px solid #0f766e;
            border-radius: 4px;
            padding: 8px 12px;
            color: #0f2a4d;
            font-size: 24px;
            font-weight: 900;
            font-family: Consolas, Segoe UI, Arial;
        }
        QPushButton#JogButton {
            background: #f8fafc;
            border: 1px solid #b8c2d0;
            font-weight: 900;
        }
        QLabel#AlertOk { background: #e6f7ef; border: 1px solid #76c99b; border-radius: 4px; color: #05603a; font-size: 15px; font-weight: 900; }
        QLabel#AlertBad { background: #fde8e8; border: 1px solid #f27b7b; border-radius: 4px; color: #9b1c1c; font-size: 15px; font-weight: 900; }
        """


def main() -> int:
    configure_logging(PROJECT_DIR / "logs")
    app = QApplication(sys.argv)
    app.setApplicationName("MORATEK SkyPharma")
    window = SupervisionWindow()
    window.show()
    return app.exec()
