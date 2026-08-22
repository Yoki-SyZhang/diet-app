"""1.6-1.8 迁移(5dfa0f2976f3):meal_entry 重建后校验字段/索引/CHECK 约束含
`llm_estimate`,以及 upgrade()/downgrade() 的空表保护——非空时必须拒绝执行,不静默丢数据。
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
PARENT_REVISION = "50b75ce1aba2"


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_meal_entry_source_tag_check_includes_llm_estimate(migrated_engine):
    inspector = inspect(migrated_engine)
    checks = inspector.get_check_constraints("meal_entry")
    sqltext = " ".join(c["sqltext"] for c in checks)
    assert len(checks) == 3
    assert "llm_estimate" in sqltext


def test_meal_entry_columns_unchanged_after_recreate(migrated_engine):
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("meal_entry")}
    assert columns == {
        "id",
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


def test_meal_entry_date_index_recreated(migrated_engine):
    inspector = inspect(migrated_engine)
    indexes = {idx["name"] for idx in inspector.get_indexes("meal_entry")}
    assert "ix_meal_entry_date" in indexes


def test_upgrade_refuses_when_meal_entry_nonempty(tmp_path, monkeypatch):
    db_url = f"sqlite:///{(tmp_path / 'nonempty_upgrade.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, PARENT_REVISION)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO meal_entry "
                "(date, meal_slot, food_name, quantity, unit, source_tag, created_at) "
                "VALUES ('2026-08-22', 'lunch', '鸡胸肉', 100, 'g', 'user_create', "
                "'2026-08-22T00:00:00Z')"
            )
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match="非空"):
        command.upgrade(cfg, "head")


def test_downgrade_refuses_when_meal_entry_nonempty(tmp_path, monkeypatch):
    db_url = f"sqlite:///{(tmp_path / 'nonempty_downgrade.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO meal_entry "
                "(date, meal_slot, food_name, quantity, unit, source_tag, created_at) "
                "VALUES ('2026-08-22', 'lunch', '熟鸡胸肉', 100, 'g', 'llm_estimate', "
                "'2026-08-22T00:00:00Z')"
            )
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match="非空"):
        command.downgrade(cfg, PARENT_REVISION)
