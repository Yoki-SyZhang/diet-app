"""food_base_us 的 run_import(config) 防护措施,和 test_demo_02_import_cli.py(cn)对称:
dry-run 不连库、未确认拒绝真实库写入、已有数据拒绝重复导入、replace 中途失败整体回滚、
数据异常默认拒绝(DataAnomalyError)、main() 的 --apply/--dry-run 参数映射。
不碰真实 backend/data/dietapp.db。
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.food_base_us import FoodBaseUs
from app.services.food_base_us_import import ParsedUsFoodRecord, UsValidationReport
from scripts import import_food_base_us as module
from scripts.import_food_base_us import (
    AlreadyImportedError,
    ConfirmationRequiredError,
    DataAnomalyError,
    EmptySourceError,
    UsImportConfig,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "usda"
FOUNDATION_JSON = FIXTURE_DIR / "cli_foundation_sample.json"
SURVEY_JSON = FIXTURE_DIR / "cli_survey_sample.json"
EMPTY_FOUNDATION_JSON = FIXTURE_DIR / "empty_foundation.json"
EMPTY_SURVEY_JSON = FIXTURE_DIR / "empty_survey.json"
# 故意在两个文件之间造出重复 fdc_id(900102),用于验证跨数据集冲突永远硬失败
COLLIDING_FOUNDATION_JSON = FIXTURE_DIR / "foundation_sample.json"
COLLIDING_SURVEY_JSON = FIXTURE_DIR / "survey_sample.json"


def db_url_of(engine) -> str:
    return str(engine.url)


def row_count(engine) -> int:
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        return session.scalar(select(func.count()).select_from(FoodBaseUs))
    finally:
        session.close()


def test_dry_run_does_not_create_any_database_connection(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "create_engine", lambda *a, **k: calls.append((a, k)))

    config = UsImportConfig(foundation_json_path=FOUNDATION_JSON, survey_json_path=SURVEY_JSON)
    report = module.run_import(config)

    assert calls == []
    assert report.records_parsed == 3


def test_confirmation_required_for_real_db_without_confirm_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "create_engine", lambda *a, **k: calls.append((a, k)))

    config = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url="",
        dry_run=False,
        confirm_real_db=False,
    )
    with pytest.raises(ConfirmationRequiredError):
        module.run_import(config)
    assert calls == []


def test_confirmation_required_even_when_explicit_url_matches_real_db(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "create_engine", lambda *a, **k: calls.append((a, k)))

    config = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=settings.database_url,
        dry_run=False,
        confirm_real_db=False,
    )
    with pytest.raises(ConfirmationRequiredError):
        module.run_import(config)
    assert calls == []


def test_cross_dataset_fdc_id_collision_always_hard_fails(migrated_engine):
    db_url = db_url_of(migrated_engine)
    config = UsImportConfig(
        foundation_json_path=COLLIDING_FOUNDATION_JSON,
        survey_json_path=COLLIDING_SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,  # 即使传了,fdc_id 冲突也不能被放行
    )
    with pytest.raises(DataAnomalyError):
        module.run_import(config)
    assert row_count(migrated_engine) == 0


def test_empty_source_files_rejected_and_does_not_wipe_existing_data(migrated_engine):
    db_url = db_url_of(migrated_engine)
    baseline = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    module.run_import(baseline)
    assert row_count(migrated_engine) == 3

    broken = UsImportConfig(
        foundation_json_path=EMPTY_FOUNDATION_JSON,
        survey_json_path=EMPTY_SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        replace=True,
        allow_anomalies=True,
    )
    with pytest.raises(EmptySourceError):
        module.run_import(broken)

    assert row_count(migrated_engine) == 3


def test_already_imported_rejected_without_replace(migrated_engine):
    db_url = db_url_of(migrated_engine)
    first = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,  # fixture 里故意有一条 data_type_mismatch
    )
    module.run_import(first)

    second = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
        replace=False,
    )
    with pytest.raises(AlreadyImportedError):
        module.run_import(second)


def test_replace_true_atomically_swaps_data(migrated_engine):
    db_url = db_url_of(migrated_engine)
    first = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    module.run_import(first)
    assert row_count(migrated_engine) == 3

    second = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
        replace=True,
    )
    module.run_import(second)
    assert row_count(migrated_engine) == 3


def test_replace_true_rolls_back_entirely_on_insert_failure(migrated_engine, monkeypatch):
    db_url = db_url_of(migrated_engine)
    baseline = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    module.run_import(baseline)
    baseline_count = row_count(migrated_engine)
    assert baseline_count == 3

    def fake_snapshot(*args, **kwargs):
        report = UsValidationReport()
        bad_records = [
            ParsedUsFoodRecord(
                fdc_id=999999,
                data_type="Foundation",
                description="重复 fdc_id A",
                kcal_100g=1.0,
                carb_100g=1.0,
                protein_100g=1.0,
                fat_100g=1.0,
                fiber_100g=1.0,
            ),
            ParsedUsFoodRecord(
                fdc_id=999999,
                data_type="Foundation",
                description="重复 fdc_id B",
                kcal_100g=2.0,
                carb_100g=2.0,
                protein_100g=2.0,
                fat_100g=2.0,
                fiber_100g=2.0,
            ),
        ]
        return bad_records, report

    monkeypatch.setattr(module, "import_food_base_us_snapshot", fake_snapshot)

    broken = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
        replace=True,
    )
    with pytest.raises(IntegrityError):
        module.run_import(broken)

    assert row_count(migrated_engine) == baseline_count


def test_data_anomaly_rejected_by_default(migrated_engine):
    db_url = db_url_of(migrated_engine)
    config = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=False,
    )
    with pytest.raises(DataAnomalyError):
        module.run_import(config)
    assert row_count(migrated_engine) == 0


def test_data_anomaly_allowed_when_flagged(migrated_engine):
    db_url = db_url_of(migrated_engine)
    config = UsImportConfig(
        foundation_json_path=FOUNDATION_JSON,
        survey_json_path=SURVEY_JSON,
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    report = module.run_import(config)
    assert report.rows_inserted == 3


def test_main_without_apply_is_dry_run_and_prints_report(capsys, tmp_path):
    # 显式传 --report-path 指向 tmp_path,避免 main() 的默认落盘位置
    # (真实的 backend/data/food_base/food_base_us/ 目录)被测试写入
    report_file = tmp_path / "report.txt"
    exit_code = module.main(
        [
            "--foundation-json",
            str(FOUNDATION_JSON),
            "--survey-json",
            str(SURVEY_JSON),
            "--report-path",
            str(report_file),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "records_parsed" in captured.out
    assert "records_parsed" in report_file.read_text(encoding="utf-8")


def test_main_with_apply_but_no_confirm_is_rejected_without_touching_real_db(capsys, tmp_path):
    exit_code = module.main(
        [
            "--foundation-json",
            str(FOUNDATION_JSON),
            "--survey-json",
            str(SURVEY_JSON),
            "--apply",
            "--report-path",
            str(tmp_path / "report.txt"),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "导入未执行" in captured.out
    assert not (tmp_path / "report.txt").exists()
