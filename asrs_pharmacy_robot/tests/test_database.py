from src.db.database import Database
from src.db.models import Medicine


def test_database_add_search_and_reduce_stock(tmp_path):
    database = Database(tmp_path / "asrs.db")
    medicine_id = database.add_medicine(
        Medicine(
            id=None,
            name="Aspirin",
            x=1.0,
            y=-2.0,
            stock=3,
            location_label="B2",
        )
    )

    medicine = database.get_medicine(medicine_id)
    assert medicine is not None
    assert medicine.name == "Aspirin"
    assert medicine.stock == 3

    results = database.search_medicines("Asp")
    assert [result.id for result in results] == [medicine_id]

    database.reduce_stock(medicine_id)
    assert database.get_medicine(medicine_id).stock == 2


def test_seed_test_medicine_is_idempotent(tmp_path):
    database = Database(tmp_path / "asrs.db")
    first_id = database.seed_test_medicine()
    second_id = database.seed_test_medicine()

    assert first_id == second_id
    assert len(database.search_medicines("TestMed_A1")) == 1

