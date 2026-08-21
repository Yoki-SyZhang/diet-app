"""1.4 food_base_cn 导入:脏值解析、去重、全空记录过滤、插入行为。
用 tests/backend/fixtures/food_base_cn/ 下手写的小 fixture,不碰真实 61 文件快照
(真实快照的精确行数验收见 test_demo_02_food_base_cn_import_real_snapshot.py)。
"""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.food_base_cn import FoodBaseCn
from app.services.food_base_cn_import import (
    ParsedFoodRecord,
    ValidationReport,
    coerce_nutrient_value,
    dedupe_by_food_code,
    filter_fully_null_records,
    insert_food_base_cn_records,
    parse_food_base_cn_directory,
    parse_record,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "food_base_cn"


def make_record(food_code: str, source_file: str = "f.json", **overrides) -> ParsedFoodRecord:
    defaults = dict(
        food_code=food_code,
        food_name="测试食物",
        edible_pct=100.0,
        kcal_100g=100.0,
        carb_100g=10.0,
        protein_100g=10.0,
        fat_100g=10.0,
        fiber_100g=1.0,
        source_commit="testcommit",
        source_file=source_file,
    )
    defaults.update(overrides)
    return ParsedFoodRecord(**defaults)


class TestCoerceNutrientValue:
    def test_ok_number(self):
        assert coerce_nutrient_value("120") == (120.0, "ok")

    def test_ok_zero_is_not_missing(self):
        assert coerce_nutrient_value("0") == (0.0, "ok")

    def test_empty_string_is_missing(self):
        assert coerce_nutrient_value("") == (None, "dirty_empty")

    def test_trace_is_missing(self):
        assert coerce_nutrient_value("Tr") == (None, "dirty_trace")

    def test_dash_is_missing(self):
        assert coerce_nutrient_value("—") == (None, "dirty_dash")

    def test_footnote_star_returns_real_number(self):
        assert coerce_nutrient_value("899*") == (899.0, "footnote_calculated")

    def test_unrecognized_string_is_missing(self):
        value, status = coerce_nutrient_value("un")
        assert value is None
        assert status == "dirty_unrecognized"

    def test_none_is_missing(self):
        assert coerce_nutrient_value(None) == (None, "dirty_empty")


class TestParseRecord:
    def test_dirty_fields_become_none_not_zero(self):
        report = ValidationReport()
        raw = {
            "foodCode": "X1",
            "foodName": "测试",
            "edible": "100",
            "energyKCal": "un",
            "protein": "Tr",
            "fat": "—",
            "CHO": "0",
            "dietaryFiber": "",
        }
        record = parse_record(raw, source_commit="c1", source_file="f.json", report=report)
        assert record.kcal_100g is None
        assert record.protein_100g is None
        assert record.fat_100g is None
        assert record.carb_100g == 0.0
        assert record.fiber_100g is None
        assert report.unrecognized_values == [("f.json", "X1", "energyKCal", "un")]

    def test_out_of_range_edible_is_recorded_but_not_dropped(self):
        report = ValidationReport()
        raw = {
            "foodCode": "X2",
            "foodName": "测试",
            "edible": "150",
            "energyKCal": "100",
            "protein": "1",
            "fat": "1",
            "CHO": "1",
            "dietaryFiber": "1",
        }
        record = parse_record(raw, source_commit="c1", source_file="f.json", report=report)
        assert record.edible_pct == 150.0
        assert report.edible_out_of_range == [("X2", 150.0)]


class TestDedupeByFoodCode:
    def test_keeps_first_occurrence_and_reports_rest(self):
        report = ValidationReport()
        records = [
            make_record("A", source_file="f1.json"),
            make_record("B", source_file="f1.json"),
            make_record("A", source_file="f2.json"),
        ]
        result = dedupe_by_food_code(records, report)
        assert [r.food_code for r in result] == ["A", "B"]
        assert result[0].source_file == "f1.json"
        assert report.duplicate_food_codes == {"A": ["f1.json", "f2.json"]}

    def test_no_duplicates_reports_empty(self):
        report = ValidationReport()
        records = [make_record("A"), make_record("B")]
        result = dedupe_by_food_code(records, report)
        assert len(result) == 2
        assert report.duplicate_food_codes == {}


class TestFilterFullyNullRecords:
    def test_excludes_record_with_all_fields_none(self):
        report = ValidationReport()
        records = [
            make_record("A"),
            make_record(
                "B",
                edible_pct=None,
                kcal_100g=None,
                carb_100g=None,
                protein_100g=None,
                fat_100g=None,
                fiber_100g=None,
            ),
        ]
        result = filter_fully_null_records(records, report)
        assert [r.food_code for r in result] == ["A"]
        assert report.fully_null_records == [("B", "测试食物")]

    def test_keeps_record_with_at_least_one_value(self):
        report = ValidationReport()
        records = [
            make_record(
                "C",
                edible_pct=None,
                kcal_100g=1.0,
                carb_100g=None,
                protein_100g=None,
                fat_100g=None,
                fiber_100g=None,
            )
        ]
        result = filter_fully_null_records(records, report)
        assert len(result) == 1
        assert report.fully_null_records == []


class TestParseFoodBaseCnDirectory:
    def test_pipeline_on_fixture_directory(self):
        records, report = parse_food_base_cn_directory(FIXTURE_DIR, source_commit="testcommit")

        assert report.files_processed == 2
        # 两个文件共 8 条原始记录(含 1 条跨文件重复 T001)
        assert report.records_parsed == 8
        assert report.duplicate_food_codes == {
            "T001": ["merged_test_a.json", "merged_test_b.json"]
        }
        assert report.fully_null_records == [("T006", "全空食物")]
        assert report.unrecognized_values == [
            ("merged_test_b.json", "T005", "energyKCal", "un")
        ]
        assert report.edible_out_of_range == [("T007", 150.0)]
        assert report.dirty_value_counts["energyKCal"]["footnote_calculated"] == 1

        # 8 条解析 - 1 条重复丢弃 - 1 条全空排除 = 6 条待插入
        codes = [r.food_code for r in records]
        assert codes == ["T001", "T002", "T003", "T004", "T005", "T007"]


class TestInsertFoodBaseCnRecords:
    def test_inserts_rows_with_utc_created_at(self, migrated_engine):
        Session = sessionmaker(bind=migrated_engine)
        session = Session()
        try:
            records = [make_record("A"), make_record("B")]
            inserted = insert_food_base_cn_records(session, records)
            session.commit()
            assert inserted == 2

            rows = session.scalars(select(FoodBaseCn)).all()
            assert len(rows) == 2
            for row in rows:
                assert row.created_at.startswith("20")
                assert "+00:00" in row.created_at or row.created_at.endswith("Z")
        finally:
            session.close()

    def test_duplicate_food_code_same_commit_raises_integrity_error(self, migrated_engine):
        Session = sessionmaker(bind=migrated_engine)
        session = Session()
        try:
            records = [
                make_record("DUP", source_commit="c1"),
                make_record("DUP", source_commit="c1"),
            ]
            with pytest.raises(IntegrityError):
                insert_food_base_cn_records(session, records)
        finally:
            session.rollback()
            session.close()
