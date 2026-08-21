"""food_base_cn 的 run_import(config) 防护措施:dry-run 不连库、未确认拒绝真实库写入、
重复导入拒绝、replace 中途失败整体回滚、数据异常默认拒绝(DataAnomalyError)、
main() 的 --apply/--dry-run 参数映射。不碰真实 backend/data/dietapp.db。
"""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.food_base_cn import FoodBaseCn
from app.services.food_base_cn_import import ParsedFoodRecord, ValidationReport
from scripts import import_food_base_cn as module
from scripts.import_food_base_cn import (
    AlreadyImportedError,
    ConfirmationRequiredError,
    DataAnomalyError,
    EmptySourceError,
    ImportConfig,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "food_base_cn"


def db_url_of(engine) -> str:
    return str(engine.url)


def row_count(engine) -> int:
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        return session.scalar(select(func.count()).select_from(FoodBaseCn))
    finally:
        session.close()


def test_dry_run_does_not_create_any_database_connection(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "create_engine", lambda *a, **k: calls.append((a, k)))

    config = ImportConfig(source_dir=FIXTURE_DIR, source_commit="c1")  # dry_run=True 默认
    report = module.run_import(config)

    assert calls == []
    assert report.records_parsed == 8


def test_confirmation_required_for_real_db_without_confirm_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "create_engine", lambda *a, **k: calls.append((a, k)))

    config = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url="",  # 空字符串 = 真实 settings.database_url
        dry_run=False,
        confirm_real_db=False,
    )
    with pytest.raises(ConfirmationRequiredError):
        module.run_import(config)

    assert calls == [], "确认参数检查必须在建立数据库连接之前完成"


def test_confirmation_required_even_when_explicit_url_matches_real_db(monkeypatch):
    # database_url 不是空字符串,而是显式传入和默认值解析结果完全相同的真实路径——
    # 不能因为字符串非空就当成"不是真实库",必须按实际 sqlite 文件路径比较
    calls = []
    monkeypatch.setattr(module, "create_engine", lambda *a, **k: calls.append((a, k)))

    config = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=settings.database_url,
        dry_run=False,
        confirm_real_db=False,
    )
    with pytest.raises(ConfirmationRequiredError):
        module.run_import(config)
    assert calls == []


def test_empty_source_dir_rejected_and_does_not_wipe_existing_data(migrated_engine, tmp_path):
    db_url = db_url_of(migrated_engine)
    baseline = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    module.run_import(baseline)
    assert row_count(migrated_engine) == 6

    empty_dir = tmp_path / "empty_source"
    empty_dir.mkdir()
    broken = ImportConfig(
        source_dir=empty_dir,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        replace=True,
        allow_anomalies=True,
    )
    with pytest.raises(EmptySourceError):
        module.run_import(broken)

    # 拒绝发生在打开数据库连接之前,--replace 的整表清空压根没有执行
    assert row_count(migrated_engine) == 6


def test_already_imported_rejected_without_replace(migrated_engine):
    db_url = db_url_of(migrated_engine)
    first = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,  # fixture 本身有重复编码/越界可食率,先放行只测重复导入这一条
    )
    module.run_import(first)

    second = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c2",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
        replace=False,
    )
    with pytest.raises(AlreadyImportedError):
        module.run_import(second)


def test_replace_true_atomically_swaps_data(migrated_engine):
    db_url = db_url_of(migrated_engine)
    first = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    module.run_import(first)
    assert row_count(migrated_engine) == 6

    second = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c2",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
        replace=True,
    )
    module.run_import(second)
    assert row_count(migrated_engine) == 6  # 整表替换,不是追加


def test_replace_true_rolls_back_entirely_on_insert_failure(migrated_engine, monkeypatch):
    db_url = db_url_of(migrated_engine)
    baseline = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    module.run_import(baseline)
    baseline_count = row_count(migrated_engine)
    assert baseline_count == 6

    def fake_parse(*args, **kwargs):
        report = ValidationReport()
        bad_records = [
            ParsedFoodRecord(
                food_code="DUP",
                food_name="重复食物 A",
                edible_pct=1.0,
                kcal_100g=1.0,
                carb_100g=1.0,
                protein_100g=1.0,
                fat_100g=1.0,
                fiber_100g=1.0,
                source_commit="c1",
                source_file="x.json",
            ),
            ParsedFoodRecord(
                food_code="DUP",
                food_name="重复食物 B",
                edible_pct=1.0,
                kcal_100g=1.0,
                carb_100g=1.0,
                protein_100g=1.0,
                fat_100g=1.0,
                fiber_100g=1.0,
                source_commit="c1",
                source_file="y.json",
            ),
        ]
        return bad_records, report

    monkeypatch.setattr(module, "parse_food_base_cn_directory", fake_parse)

    broken = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
        replace=True,
    )
    with pytest.raises(IntegrityError):
        module.run_import(broken)

    # 旧数据的 DELETE 和新数据的 INSERT 包在同一事务里,失败后整体回滚,行数不变
    assert row_count(migrated_engine) == baseline_count


def test_data_anomaly_rejected_by_default(migrated_engine):
    db_url = db_url_of(migrated_engine)
    config = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=False,
    )
    with pytest.raises(DataAnomalyError):
        module.run_import(config)
    assert row_count(migrated_engine) == 0


def test_data_anomaly_allowed_when_flagged(migrated_engine):
    db_url = db_url_of(migrated_engine)
    config = ImportConfig(
        source_dir=FIXTURE_DIR,
        source_commit="c1",
        database_url=db_url,
        dry_run=False,
        allow_anomalies=True,
    )
    report = module.run_import(config)
    assert report.rows_inserted == 6


def test_main_without_apply_is_dry_run_and_prints_report(capsys, tmp_path):
    # 显式传 --report-path 指向 tmp_path,避免 main() 的默认落盘位置
    # (source-dir/import_report.txt)污染仓库里的 fixture 目录
    report_file = tmp_path / "report.txt"
    exit_code = module.main(
        [
            "--source-dir",
            str(FIXTURE_DIR),
            "--source-commit",
            "c1",
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
            "--source-dir",
            str(FIXTURE_DIR),
            "--source-commit",
            "c1",
            "--apply",
            "--report-path",
            str(tmp_path / "report.txt"),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "导入未执行" in captured.out
    assert not (tmp_path / "report.txt").exists()
