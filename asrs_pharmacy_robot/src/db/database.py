from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from src.db.models import Medicine


class Database:
    def __init__(self, db_path: str | Path = "data/asrs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        with self.connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))

    def add_medicine(self, medicine: Medicine) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO medicines
                    (name, x, y, stock, location_label, category, expiry_date, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    medicine.name,
                    medicine.x,
                    medicine.y,
                    medicine.stock,
                    medicine.location_label,
                    medicine.category,
                    medicine.expiry_date,
                    int(medicine.is_active),
                ),
            )
            return int(cursor.lastrowid)

    def update_medicine(self, medicine: Medicine) -> None:
        if medicine.id is None:
            raise ValueError("Cannot update medicine without an id")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE medicines
                SET name = ?, x = ?, y = ?, stock = ?, location_label = ?,
                    category = ?, expiry_date = ?, is_active = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    medicine.name,
                    medicine.x,
                    medicine.y,
                    medicine.stock,
                    medicine.location_label,
                    medicine.category,
                    medicine.expiry_date,
                    int(medicine.is_active),
                    medicine.id,
                ),
            )

    def deactivate_medicine(self, medicine_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE medicines
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (medicine_id,),
            )

    def get_medicine(self, medicine_id: int) -> Medicine | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM medicines WHERE id = ? AND is_active = 1",
                (medicine_id,),
            ).fetchone()
        return self._row_to_medicine(row) if row else None

    def search_medicines(self, query: str = "") -> list[Medicine]:
        search = f"%{query}%"
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM medicines
                WHERE is_active = 1 AND (name LIKE ? OR CAST(id AS TEXT) LIKE ?)
                ORDER BY name
                """,
                (search, search),
            ).fetchall()
        return [self._row_to_medicine(row) for row in rows]

    def reduce_stock(self, medicine_id: int, amount: int = 1) -> None:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE medicines
                SET stock = stock - ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND stock >= ?
                """,
                (amount, medicine_id, amount),
            )
            if cursor.rowcount != 1:
                raise ValueError("Stock could not be reduced")

    def log_dispense(
        self,
        medicine: Medicine | None,
        status: str,
        message: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dispense_history
                    (medicine_id, medicine_name, x, y, status, message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    medicine.id if medicine else None,
                    medicine.name if medicine else None,
                    medicine.x if medicine else None,
                    medicine.y if medicine else None,
                    status,
                    message,
                ),
            )

    def log_machine_event(self, event_type: str, message: str, grbl_state: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO machine_events (event_type, message, grbl_state)
                VALUES (?, ?, ?)
                """,
                (event_type, message, grbl_state),
            )

    def dispense_history(self, limit: int = 50) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM dispense_history ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def machine_events(self, limit: int = 50) -> Iterable[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM machine_events ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    def seed_test_medicine(self) -> int:
        existing = self.search_medicines("TestMed_A1")
        for medicine in existing:
            if medicine.name == "TestMed_A1":
                return int(medicine.id)
        return self.add_medicine(
            Medicine(
                id=None,
                name="TestMed_A1",
                x=2.0,
                y=-9.1,
                stock=10,
                location_label="A1",
            )
        )

    @staticmethod
    def _row_to_medicine(row: sqlite3.Row) -> Medicine:
        return Medicine(
            id=int(row["id"]),
            name=str(row["name"]),
            x=float(row["x"]),
            y=float(row["y"]),
            stock=int(row["stock"]),
            location_label=row["location_label"],
            category=row["category"],
            expiry_date=row["expiry_date"],
            is_active=bool(row["is_active"]),
        )
