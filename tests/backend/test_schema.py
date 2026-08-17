from sqlalchemy import inspect

DEMO_TABLES = ("meal_entry", "daily_summary", "chat_message", "food_base_cn", "food_base_us")

NULLABLE_NUTRIENT_COLUMNS = {
    "meal_entry": ["kcal", "carb_g", "protein_g", "fat_g", "fiber_g"],
    "daily_summary": [
        "total_kcal",
        "total_carb_g",
        "total_protein_g",
        "total_fat_g",
        "total_fiber_g",
        "bmr_snapshot",
    ],
    "food_base_cn": [
        "edible_pct",
        "kcal_100g",
        "carb_100g",
        "protein_100g",
        "fat_100g",
        "fiber_100g",
    ],
    "food_base_us": ["kcal_100g", "carb_100g", "protein_100g", "fat_100g", "fiber_100g"],
}


def test_all_demo_tables_exist(migrated_engine):
    inspector = inspect(migrated_engine)
    tables = set(inspector.get_table_names())
    assert set(DEMO_TABLES).issubset(tables)


def test_no_table_has_user_id(migrated_engine):
    inspector = inspect(migrated_engine)
    for table in DEMO_TABLES:
        columns = {c["name"] for c in inspector.get_columns(table)}
        assert "user_id" not in columns, f"{table} 不应有 user_id(单用户系统铁律)"


def test_nutrient_columns_are_nullable_not_defaulted_to_zero(migrated_engine):
    inspector = inspect(migrated_engine)
    for table, cols in NULLABLE_NUTRIENT_COLUMNS.items():
        by_name = {c["name"]: c for c in inspector.get_columns(table)}
        for col in cols:
            assert by_name[col]["nullable"] is True, f"{table}.{col} 应为 nullable"
            assert by_name[col]["default"] is None, f"{table}.{col} 不应有默认值(避免误当 0)"


def test_daily_summary_primary_key_is_date_only(migrated_engine):
    inspector = inspect(migrated_engine)
    pk = inspector.get_pk_constraint("daily_summary")
    assert pk["constrained_columns"] == ["date"]


def test_food_base_cn_unique_on_code_and_source_commit(migrated_engine):
    inspector = inspect(migrated_engine)
    uniques = inspector.get_unique_constraints("food_base_cn")
    assert any(
        set(u["column_names"]) == {"food_code", "source_commit"} for u in uniques
    ), "food_base_cn 应允许不同 source_commit 下同一 food_code 并存"


def test_food_base_us_primary_key_is_fdc_id(migrated_engine):
    inspector = inspect(migrated_engine)
    pk = inspector.get_pk_constraint("food_base_us")
    assert pk["constrained_columns"] == ["fdc_id"]


def test_meal_entry_enum_check_constraints_use_synced_spec_literals(migrated_engine):
    inspector = inspect(migrated_engine)
    checks = inspector.get_check_constraints("meal_entry")
    sqltext = " ".join(c["sqltext"] for c in checks)
    assert len(checks) == 3, "meal_slot/unit/source_tag 三个枚举都应落成 CHECK 约束"
    assert "other" in sqltext
    assert "snack" not in sqltext
    assert "decompose_estimate" in sqltext
    assert "web_estimate" not in sqltext
