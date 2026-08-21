"""1.5 food_base_us 导入:跳过数组里的 null 占位项、missing_nutrient_counts 统计、
dataType 一致性校验、跨数据集 fdc_id 冲突检测、insert_food_base_us_records 插入行为。
用 tests/backend/fixtures/usda/foundation_sample.json + survey_sample.json 两个手写
小 fixture(不是真实 5795 条快照,真实数字验收见 test_demo_02_food_base_us_import_real_snapshot.py)。
"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.food_base_us import FoodBaseUs
from app.services.food_base_us_import import (
    import_food_base_us_snapshot,
    insert_food_base_us_records,
    parse_us_food_base_file,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "usda"
FOUNDATION_SAMPLE = FIXTURE_DIR / "foundation_sample.json"
SURVEY_SAMPLE = FIXTURE_DIR / "survey_sample.json"


class TestParseUsFoodBaseFile:
    def test_skips_null_array_entries(self):
        records, report = parse_us_food_base_file(FOUNDATION_SAMPLE, expected_data_type="Foundation")
        # 数组里放了 1 个 null + 3 条真实记录
        assert report.array_entries_total == 4
        assert report.null_array_entries_skipped == 1
        assert report.records_parsed == 3
        assert len(records) == 3

    def test_data_type_mismatch_is_recorded_not_dropped(self):
        records, report = parse_us_food_base_file(FOUNDATION_SAMPLE, expected_data_type="Foundation")
        assert report.data_type_mismatches == [900101]
        # 不因为 dataType 不符就丢弃这条记录
        assert any(r.fdc_id == 900101 for r in records)

    def test_missing_nutrient_counts(self):
        _, report = parse_us_food_base_file(FOUNDATION_SAMPLE, expected_data_type="Foundation")
        # 746775(Salt)五项全缺;900101/900102 只有 kcal,其余 4 项缺
        assert report.missing_nutrient_counts["kcal"] == 1
        assert report.missing_nutrient_counts["protein"] == 3
        assert report.missing_nutrient_counts["fat"] == 3
        assert report.missing_nutrient_counts["carb"] == 3
        assert report.missing_nutrient_counts["fiber"] == 3

    def test_single_file_never_computes_cross_dataset_collisions(self):
        _, report = parse_us_food_base_file(FOUNDATION_SAMPLE, expected_data_type="Foundation")
        assert report.cross_dataset_fdc_id_collisions == []
        assert report.files_processed == 1


class TestImportFoodBaseUsSnapshot:
    def test_merges_reports_from_both_files(self):
        records, report = import_food_base_us_snapshot(FOUNDATION_SAMPLE, SURVEY_SAMPLE)
        assert report.files_processed == 2
        assert report.array_entries_total == 4 + 2
        assert report.null_array_entries_skipped == 1
        assert report.records_parsed == 3 + 2
        assert len(records) == 5

    def test_detects_cross_dataset_fdc_id_collision(self):
        _, report = import_food_base_us_snapshot(FOUNDATION_SAMPLE, SURVEY_SAMPLE)
        assert report.cross_dataset_fdc_id_collisions == [900102]

    def test_does_not_touch_database(self):
        # 纯函数,不接收/不创建任何 session——这里只是确认调用不需要数据库依赖
        records, report = import_food_base_us_snapshot(FOUNDATION_SAMPLE, SURVEY_SAMPLE)
        assert report.rows_inserted == 0
        assert isinstance(records, list)


class TestInsertFoodBaseUsRecords:
    def test_inserts_rows_with_utc_created_at(self, migrated_engine):
        # 只用 foundation_sample(3 条,fdc_id 互不重复)——merge 后的 5 条里故意有
        # 一对跨文件重复的 fdc_id(用于上面 cross_dataset_fdc_id_collisions 测试),
        # 不能直接拿来测插入,否则会撞 fdc_id 主键,这属于测试数据的预期冲突不是 bug。
        records, _ = parse_us_food_base_file(FOUNDATION_SAMPLE, expected_data_type="Foundation")
        Session = sessionmaker(bind=migrated_engine)
        session = Session()
        try:
            inserted = insert_food_base_us_records(session, records)
            session.commit()
            assert inserted == len(records)

            rows = session.scalars(select(FoodBaseUs)).all()
            assert len(rows) == len(records)
            for row in rows:
                assert row.created_at.startswith("20")
        finally:
            session.close()
