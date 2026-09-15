from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from src.core.asrs_controller import ASRSController
from src.core.machine_config import MachineConfig
from src.db.database import Database
from src.db.models import Medicine
from src.utils.logger import configure_logging

try:
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - handled in the UI at runtime
    list_ports = None


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_DIR / "config" / "machine_config.json"
DEFAULT_DB = PROJECT_DIR / "data" / "asrs.db"


class TaskWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, task: Callable[[], Any]):
        super().__init__()
        self.task = task

    def run(self) -> None:
        try:
            self.finished.emit(self.task())
        except Exception as exc:  # pragma: no cover - driven by GUI integration
            self.failed.emit(str(exc))


class MedicineDialog(QDialog):
    def __init__(self, parent: QWidget, medicine: Medicine | None = None):
        super().__init__(parent)
        self.setWindowTitle("Medicament")
        self._medicine_id = medicine.id if medicine else None

        self.name_edit = QLineEdit(medicine.name if medicine else "")
        self.location_edit = QLineEdit(medicine.location_label or "" if medicine else "")
        self.category_edit = QLineEdit(medicine.category or "" if medicine else "")
        self.expiry_edit = QLineEdit(medicine.expiry_date or "" if medicine else "")

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-1000.0, 1000.0)
        self.x_spin.setDecimals(3)
        self.x_spin.setValue(medicine.x if medicine else 0.0)

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-1000.0, 1000.0)
        self.y_spin.setDecimals(3)
        self.y_spin.setValue(medicine.y if medicine else 0.0)

        self.stock_spin = QSpinBox()
        self.stock_spin.setRange(0, 100000)
        self.stock_spin.setValue(medicine.stock if medicine else 0)

        form = QFormLayout()
        form.addRow("Nom", self.name_edit)
        form.addRow("X", self.x_spin)
        form.addRow("Y", self.y_spin)
        form.addRow("Stock", self.stock_spin)
        form.addRow("Case", self.location_edit)
        form.addRow("Categorie", self.category_edit)
        form.addRow("Expiration", self.expiry_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def medicine(self) -> Medicine:
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError("Le nom du medicament est obligatoire")
        return Medicine(
            id=self._medicine_id,
            name=name,
            x=self.x_spin.value(),
            y=self.y_spin.value(),
            stock=self.stock_spin.value(),
            location_label=self.location_edit.text().strip() or None,
            category=self.category_edit.text().strip() or None,
            expiry_date=self.expiry_edit.text().strip() or None,
        )


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path = DEFAULT_CONFIG, db_path: Path = DEFAULT_DB):
        super().__init__()
        self.setWindowTitle("SkyPharma ASRS - Commande medicaments")
        self.resize(1180, 760)

        self.config = MachineConfig.from_json(config_path)
        self.database = Database(db_path)
        self.controller = ASRSController(self.config, self.database)
        self.selected_medicine: Medicine | None = None
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None

        self._build_ui()
        self.refresh_ports()
        self.refresh_medicines()
        self.refresh_logs()
        self.update_connection_state()

    def _build_ui(self) -> None:
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Pret")

        toolbar = QToolBar("Machine", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        seed_action = QAction("Ajouter TestMed_A1", self)
        seed_action.triggered.connect(self.seed_test_medicine)
        toolbar.addAction(seed_action)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        top = QHBoxLayout()
        layout.addLayout(top)
        top.addWidget(self._connection_group(), 2)
        top.addWidget(self._machine_group(), 3)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        splitter.addWidget(self._medicine_group())
        splitter.addWidget(self._right_tabs())
        splitter.setSizes([660, 520])

    def _connection_group(self) -> QGroupBox:
        group = QGroupBox("Connexion GRBL")
        layout = QGridLayout(group)

        self.port_combo = QComboBox()
        self.refresh_ports_button = QPushButton("Actualiser")
        self.connect_button = QPushButton("Connecter")
        self.disconnect_button = QPushButton("Deconnecter")
        self.connection_label = QLabel("Deconnecte")
        self.grbl_state_label = QLabel("-")

        self.refresh_ports_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.connect_machine)
        self.disconnect_button.clicked.connect(self.disconnect_machine)

        layout.addWidget(QLabel("Port COM"), 0, 0)
        layout.addWidget(self.port_combo, 0, 1)
        layout.addWidget(self.refresh_ports_button, 0, 2)
        layout.addWidget(self.connect_button, 1, 1)
        layout.addWidget(self.disconnect_button, 1, 2)
        layout.addWidget(QLabel("Etat"), 2, 0)
        layout.addWidget(self.connection_label, 2, 1, 1, 2)
        layout.addWidget(QLabel("GRBL"), 3, 0)
        layout.addWidget(self.grbl_state_label, 3, 1, 1, 2)
        return group

    def _machine_group(self) -> QGroupBox:
        group = QGroupBox("Controle machine")
        layout = QGridLayout(group)

        self.home_button = QPushButton("Homing $H")
        self.unlock_button = QPushButton("Reset alarme $X")
        self.stop_button = QPushButton("Stop !")
        self.resume_button = QPushButton("Resume ~")
        self.soft_reset_button = QPushButton("Soft reset")
        self.position_button = QPushButton("Lire position")
        self.position_label = QLabel("X ---.---   Y ---.---   Z ---.---")

        self.home_button.clicked.connect(lambda: self.run_task("Homing", self.controller.home))
        self.unlock_button.clicked.connect(lambda: self.run_task("Reset alarme", self.controller.reset_alarm))
        self.stop_button.clicked.connect(self.stop_machine)
        self.resume_button.clicked.connect(lambda: self.run_task("Resume", self.controller.resume))
        self.soft_reset_button.clicked.connect(lambda: self.run_task("Soft reset", self.controller.soft_reset))
        self.position_button.clicked.connect(self.read_position)

        buttons = [
            self.home_button,
            self.unlock_button,
            self.stop_button,
            self.resume_button,
            self.soft_reset_button,
            self.position_button,
        ]
        for index, button in enumerate(buttons):
            layout.addWidget(button, index // 3, index % 3)
        layout.addWidget(self.position_label, 2, 0, 1, 3)
        return group

    def _medicine_group(self) -> QGroupBox:
        group = QGroupBox("Medicaments")
        layout = QVBoxLayout(group)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Rechercher par nom ou ID")
        self.search_edit.textChanged.connect(self.refresh_medicines)
        self.add_button = QPushButton("Ajouter")
        self.edit_button = QPushButton("Modifier")
        self.delete_button = QPushButton("Desactiver")
        self.add_button.clicked.connect(self.add_medicine)
        self.edit_button.clicked.connect(self.edit_medicine)
        self.delete_button.clicked.connect(self.deactivate_medicine)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.add_button)
        search_row.addWidget(self.edit_button)
        search_row.addWidget(self.delete_button)

        self.medicine_table = QTableWidget(0, 6)
        self.medicine_table.setHorizontalHeaderLabels(["ID", "Nom", "X", "Y", "Stock", "Case"])
        self.medicine_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.medicine_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.medicine_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.medicine_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.medicine_table.itemSelectionChanged.connect(self.on_medicine_selected)
        self.medicine_table.doubleClicked.connect(self.edit_medicine)

        self.dispense_button = QPushButton("Distribuer le medicament selectionne")
        self.preview_button = QPushButton("Generer apercu G-code")
        self.dispense_button.clicked.connect(self.confirm_dispense)
        self.preview_button.clicked.connect(self.preview_gcode)

        action_row = QHBoxLayout()
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.dispense_button)

        layout.addLayout(search_row)
        layout.addWidget(self.medicine_table, 1)
        layout.addLayout(action_row)
        return group

    def _right_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        self.gcode_preview = QTextEdit()
        self.gcode_preview.setReadOnly(True)
        self.gcode_preview.setPlaceholderText("L'apercu G-code apparait ici")
        tabs.addTab(self.gcode_preview, "G-code")

        self.history_table = QTableWidget(0, 6)
        self.history_table.setHorizontalHeaderLabels(["Date", "ID", "Nom", "X", "Y", "Statut"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabs.addTab(self.history_table, "Historique")

        self.events_table = QTableWidget(0, 4)
        self.events_table.setHorizontalHeaderLabels(["Date", "Type", "Message", "GRBL"])
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabs.addTab(self.events_table, "Evenements")
        return tabs

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = []
        if list_ports is not None:
            ports = [port.device for port in list_ports.comports()]
        self.port_combo.addItems(ports or ["COM5"])
        if current:
            index = self.port_combo.findText(current)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)

    def connect_machine(self) -> None:
        port = self.port_combo.currentText().strip()
        if not port:
            self.show_error("Choisis un port COM")
            return
        self.run_task(f"Connexion {port}", lambda: self.controller.connect_machine(port))

    def disconnect_machine(self) -> None:
        self.controller.disconnect_machine()
        self.update_connection_state()
        self.refresh_logs()
        self.statusBar().showMessage("Machine deconnectee")

    def stop_machine(self) -> None:
        try:
            self.controller.stop()
            self.update_connection_state()
            self.refresh_logs()
        except Exception as exc:
            self.show_error(str(exc))

    def read_position(self) -> None:
        def done(position: tuple[float, float, float]) -> None:
            self.position_label.setText(
                f"X {position[0]:.3f}   Y {position[1]:.3f}   Z {position[2]:.3f}"
            )

        self.run_task("Lecture position", self.controller.get_position, done)

    def refresh_medicines(self) -> None:
        medicines = self.database.search_medicines(self.search_edit.text().strip() if hasattr(self, "search_edit") else "")
        self.medicine_table.setRowCount(len(medicines))
        for row_index, medicine in enumerate(medicines):
            values = [
                medicine.id,
                medicine.name,
                f"{medicine.x:.3f}",
                f"{medicine.y:.3f}",
                medicine.stock,
                medicine.location_label or "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, medicine)
                self.medicine_table.setItem(row_index, column, item)
        self.on_medicine_selected()

    def on_medicine_selected(self) -> None:
        items = self.medicine_table.selectedItems()
        self.selected_medicine = items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def add_medicine(self) -> None:
        dialog = MedicineDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.database.add_medicine(dialog.medicine())
                self.refresh_medicines()
            except Exception as exc:
                self.show_error(str(exc))

    def edit_medicine(self) -> None:
        if self.selected_medicine is None:
            self.show_error("Selectionne un medicament")
            return
        dialog = MedicineDialog(self, self.selected_medicine)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.database.update_medicine(dialog.medicine())
                self.refresh_medicines()
            except Exception as exc:
                self.show_error(str(exc))

    def deactivate_medicine(self) -> None:
        if self.selected_medicine is None or self.selected_medicine.id is None:
            self.show_error("Selectionne un medicament")
            return
        reply = QMessageBox.question(
            self,
            "Desactiver",
            f"Desactiver {self.selected_medicine.name} ?",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.database.deactivate_medicine(self.selected_medicine.id)
            self.refresh_medicines()

    def seed_test_medicine(self) -> None:
        medicine_id = self.database.seed_test_medicine()
        self.refresh_medicines()
        self.statusBar().showMessage(f"TestMed_A1 pret avec ID {medicine_id}")

    def preview_gcode(self) -> None:
        if self.selected_medicine is None or self.selected_medicine.id is None:
            self.show_error("Selectionne un medicament")
            return
        try:
            program = self.controller.preview_dispense(self.selected_medicine.id)
            self.gcode_preview.setPlainText("\n".join(program))
        except Exception as exc:
            self.show_error(str(exc))

    def confirm_dispense(self) -> None:
        if self.selected_medicine is None or self.selected_medicine.id is None:
            self.show_error("Selectionne un medicament")
            return
        self.preview_gcode()
        reply = QMessageBox.question(
            self,
            "Confirmer distribution",
            f"Envoyer le robot chercher {self.selected_medicine.name} ?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        medicine_id = self.selected_medicine.id
        self.run_task(
            "Distribution",
            lambda: self.controller.distribute_medicine(medicine_id),
            lambda program: self.gcode_preview.setPlainText("\n".join(program)),
        )

    def refresh_logs(self) -> None:
        history = list(self.database.dispense_history())
        self.history_table.setRowCount(len(history))
        for row_index, row in enumerate(history):
            values = [
                row["created_at"],
                row["medicine_id"] or "",
                row["medicine_name"] or "",
                "" if row["x"] is None else f"{row['x']:.3f}",
                "" if row["y"] is None else f"{row['y']:.3f}",
                row["status"],
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row_index, column, QTableWidgetItem(str(value)))

        events = list(self.database.machine_events())
        self.events_table.setRowCount(len(events))
        for row_index, row in enumerate(events):
            values = [row["created_at"], row["event_type"], row["message"] or "", row["grbl_state"] or ""]
            for column, value in enumerate(values):
                self.events_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def run_task(
        self,
        label: str,
        task: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
    ) -> None:
        if self._thread is not None:
            self.show_error("Une commande machine est deja en cours")
            return
        self.set_busy(True, label)
        self._thread = QThread(self)
        self._worker = TaskWorker(task)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(lambda result: self._task_finished(label, result, on_success))
        self._worker.failed.connect(lambda message: self._task_failed(label, message))
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _task_finished(
        self,
        label: str,
        result: Any,
        on_success: Callable[[Any], None] | None,
    ) -> None:
        if on_success is not None:
            on_success(result)
        self.set_busy(False, label)
        self.update_connection_state()
        self.refresh_medicines()
        self.refresh_logs()
        self.statusBar().showMessage(f"{label} termine")

    def _task_failed(self, label: str, message: str) -> None:
        self.set_busy(False, label)
        self.update_connection_state()
        self.refresh_logs()
        self.show_error(f"{label}: {message}")

    def _cleanup_thread(self) -> None:
        self._thread = None
        self._worker = None

    def set_busy(self, busy: bool, label: str) -> None:
        for widget in [
            self.connect_button,
            self.disconnect_button,
            self.home_button,
            self.unlock_button,
            self.resume_button,
            self.soft_reset_button,
            self.position_button,
            self.dispense_button,
        ]:
            widget.setEnabled(not busy)
        self.stop_button.setEnabled(self.controller.grbl.is_connected())
        if busy:
            self.statusBar().showMessage(f"{label} en cours...")

    def update_connection_state(self) -> None:
        connected = self.controller.grbl.is_connected()
        self.connection_label.setText("Connecte" if connected else "Deconnecte")
        self.grbl_state_label.setText(str(self.controller.state))
        self.disconnect_button.setEnabled(connected)
        self.home_button.setEnabled(connected)
        self.unlock_button.setEnabled(connected)
        self.stop_button.setEnabled(connected)
        self.resume_button.setEnabled(connected)
        self.soft_reset_button.setEnabled(connected)
        self.position_button.setEnabled(connected)

    def show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Erreur", message)
        self.statusBar().showMessage(message)


def main() -> int:
    configure_logging(PROJECT_DIR / "logs")
    app = QApplication(sys.argv)
    app.setApplicationName("SkyPharma ASRS")
    window = MainWindow()
    window.show()
    return app.exec()
