"""1.9 迁移(aa2972598fa7):meal_entry 加 confirmation_id 幂等键列+唯一索引,
chat_message 加 batch_id/kind/food_summary_json 批次追踪三列;upgrade()/downgrade()
的空表保护——任一表非空时必须拒绝执行,不静默丢数据(沿用 5dfa0f2976f3 的安全模式)。
只在临时 SQLite 上跑,不碰真实库。
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, exc, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
PARENT_REVISION = "5dfa0f2976f3"


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_meal_entry_confirmation_id_column_added(migrated_engine):
    inspector = inspect(migrated_engine)
    columns = {c["name"]: c for c in inspector.get_columns("meal_entry")}
    assert "confirmation_id" in columns
    assert columns["confirmation_id"]["nullable"] is False


def test_meal_entry_confirmation_id_unique_index(migrated_engine):
    inspector = inspect(migrated_engine)
    indexes = {idx["name"]: idx for idx in inspector.get_indexes("meal_entry")}
    assert "ix_meal_entry_confirmation_id" in indexes
    assert indexes["ix_meal_entry_confirmation_id"]["unique"]
    assert indexes["ix_meal_entry_confirmation_id"]["column_names"] == ["confirmation_id"]
    # 原有 date 索引不受影响
    assert "ix_meal_entry_date" in indexes


def test_meal_entry_existing_columns_survive_batch_recreate(migrated_engine):
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("meal_entry")}
    assert columns == {
        "id",
        "confirmation_id",
        "date",
        "meal_slot",
        "food_name",
        "quantity",
        "unit",
        "kcal",
        "carb_g",
        "protein_g",
        "fat_g",
        "fiber_g",
        "source_tag",
        "created_at",
    }
    # batch 重建后 CHECK 约束仍在(meal_slot/unit/source_tag 三条)
    checks = inspector.get_check_constraints("meal_entry")
    assert len(checks) == 3


def test_chat_message_batch_tracking_columns_added(migrated_engine):
    inspector = inspect(migrated_engine)
    columns = {c["name"]: c for c in inspector.get_columns("chat_message")}
    for name in ("batch_id", "kind", "food_summary_json"):
        assert name in columns
        assert columns[name]["nullable"] is True


def test_duplicate_confirmation_id_rejected_by_unique_index(migrated_engine):
    insert_sql = text(
        "INSERT INTO meal_entry "
        "(confirmation_id, date, meal_slot, food_name, quantity, unit, source_tag, created_at) "
        "VALUES (:cid, '2026-08-24', 'lunch', '熟鸡胸肉', 150, 'g', 'llm_estimate', "
        "'2026-08-24T00:00:00+00:00')"
    )
    with migrated_engine.begin() as conn:
        conn.execute(insert_sql, {"cid": "conf-1"})
    with pytest.raises(exc.IntegrityError):
        with migrated_engine.begin() as conn:
            conn.execute(insert_sql, {"cid": "conf-1"})


@pytest.mark.parametrize("table", ["meal_entry", "chat_message"])
def test_upgrade_refuses_when_table_nonempty(tmp_path, monkeypatch, table):
    db_url = f"sqlite:///{(tmp_path / f'nonempty_upgrade_{table}.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, PARENT_REVISION)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        if table == "meal_entry":
            conn.execute(
                text(
                    "INSERT INTO meal_entry "
                    "(date, meal_slot, food_name, quantity, unit, source_tag, created_at) "
                    "VALUES ('2026-08-24', 'lunch', '熟鸡胸肉', 100, 'g', 'llm_estimate', "
                    "'2026-08-24T00:00:00+00:00')"
                )
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO chat_message (date, role, content, created_at) "
                    "VALUES ('2026-08-24', 'user', '我吃了点东西', '2026-08-24T00:00:00+00:00')"
                )
            )
    engine.dispose()

    with pytest.raises(RuntimeError, match="非空"):
        command.upgrade(cfg, "head")


@pytest.mark.parametrize("table", ["meal_entry", "chat_message"])
def test_downgrade_refuses_when_table_nonempty(tmp_path, monkeypatch, table):
    db_url = f"sqlite:///{(tmp_path / f'nonempty_downgrade_{table}.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        if table == "meal_entry":
            conn.execute(
                text(
                    "INSERT INTO meal_entry "
                    "(confirmation_id, date, meal_slot, food_name, quantity, unit, "
                    "source_tag, created_at) "
                    "VALUES ('conf-1', '2026-08-24', 'lunch', '熟鸡胸肉', 100, 'g', "
                    "'llm_estimate', '2026-08-24T00:00:00+00:00')"
                )
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO chat_message (date, role, content, created_at) "
                    "VALUES ('2026-08-24', 'user', '我吃了点东西', '2026-08-24T00:00:00+00:00')"
                )
            )
    engine.dispose()

    with pytest.raises(RuntimeError, match="非空"):
        command.downgrade(cfg, PARENT_REVISION)


def test_downgrade_on_empty_tables_restores_previous_schema(tmp_path, monkeypatch):
    db_url = f"sqlite:///{(tmp_path / 'empty_roundtrip.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, PARENT_REVISION)

    engine = create_engine(db_url)
    inspector = inspect(engine)
    meal_columns = {c["name"] for c in inspector.get_columns("meal_entry")}
    chat_columns = {c["name"] for c in inspector.get_columns("chat_message")}
    engine.dispose()

    assert "confirmation_id" not in meal_columns
    assert {"batch_id", "kind", "food_summary_json"}.isdisjoint(chat_columns)
