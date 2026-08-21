"""food_base_us 导入 CLI(SPEC §4.4.2,维护模型见 ADR 0005)。和 import_food_base_cn.py
结构对称:唯一能打开真实 backend/data/dietapp.db 的入口(针对 food_base_us),默认
dry-run,--apply --confirm-real-db 两个参数同时传才会真的写真实库。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.models.food_base_us import FoodBaseUs
from app.services.food_base_us_import import (
    UsValidationReport,
    import_food_base_us_snapshot,
    insert_food_base_us_records,
)
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

_US_BASE_DIR = Path(__file__).resolve().parents[1] / "data" / "food_base" / "food_base_us"
DEFAULT_FOUNDATION_JSON = (
    _US_BASE_DIR
    / "foundation_food_json_2026-04-30"
    / "FoodData_Central_foundation_food_json_2026-04-30.json"
)
DEFAULT_SURVEY_JSON = (
    _US_BASE_DIR
    / "survey_food_json_2024-10-31"
    / "FoodData_Central_survey_food_json_2024-10-31.json"
)


class AlreadyImportedError(Exception):
    """food_base_us 表里已有任何行且未传 --replace(和 cn 对称)。"""


class ConfirmationRequiredError(Exception):
    """非 dry-run 且指向真实 dietapp.db 但未传 --confirm-real-db。"""


class DataAnomalyError(Exception):
    """report.data_type_mismatches 非空且未传 --allow-anomalies,或
    report.cross_dataset_fdc_id_collisions 非空(后者永远硬失败,--allow-anomalies
    救不了——fdc_id 是主键,插入两条同 fdc_id 的记录必然撞唯一约束,放行没有意义,
    必须先回去核对两个源文件本身)。"""


class EmptySourceError(Exception):
    """两个下载文件没有解析出任何可插入记录——多半是路径配错,不能配合 --replace
    先清空整表再插入 0 行。不受 --allow-anomalies 影响,永远硬失败。"""


@dataclass
class UsImportConfig:
    foundation_json_path: Path = DEFAULT_FOUNDATION_JSON
    survey_json_path: Path = DEFAULT_SURVEY_JSON
    database_url: str = ""  # 空字符串代表用 settings.database_url(即真实文件)
    dry_run: bool = True
    confirm_real_db: bool = False
    replace: bool = False
    allow_anomalies: bool = False
    report_path: Path | None = None  # None = 不落盘,只有 main() 会给出默认路径


def _targets_real_db(database_url: str) -> bool:
    """和 import_food_base_cn.py 的同名函数一致:按实际 sqlite 文件路径比较,不能
    只看 database_url 是不是空字符串,否则显式传入和默认值相同的真实路径会绕过
    --confirm-real-db 检查。"""
    resolved = database_url or settings.database_url
    real = settings.database_url
    resolved_url = make_url(resolved)
    real_url = make_url(real)
    if not resolved_url.drivername.startswith("sqlite") or not real_url.drivername.startswith(
        "sqlite"
    ):
        return resolved == real
    if not resolved_url.database or not real_url.database:
        return resolved == real
    return Path(resolved_url.database).resolve() == Path(real_url.database).resolve()


def run_import(config: UsImportConfig) -> UsValidationReport:
    """和 food_base_cn 的 run_import 同样的防护措施,内部调用 import_food_base_us_snapshot
    (两个文件的协调入口),不是直接调 parse_us_food_base_file:
    - dry_run=True(默认):只跑 import_food_base_us_snapshot,完全不建数据库连接。
    - dry_run=False 且没有解析出任何可插入记录:抛 EmptySourceError,不写库。
    - dry_run=False 且指向真实库(按实际 sqlite 文件路径比较)但 confirm_real_db=False:
      抛 ConfirmationRequiredError。
    - dry_run=False 且 report.cross_dataset_fdc_id_collisions 非空:永远抛 DataAnomalyError,
      不受 allow_anomalies 影响——fdc_id 是主键,插入时必然真实撞唯一约束。
    - dry_run=False 且 report.data_type_mismatches 非空且 allow_anomalies=False:
      抛 DataAnomalyError,不写库。
    - dry_run=False 且表里已有任何行且 replace=False:抛 AlreadyImportedError。
    - dry_run=False 且 replace=True:整表 DELETE + 全部记录 INSERT 包在同一显式事务里。
    """
    records, report = import_food_base_us_snapshot(
        config.foundation_json_path, config.survey_json_path
    )

    if config.dry_run:
        _maybe_write_report(config, report)
        return report

    if not records:
        raise EmptySourceError(
            "Foundation/Survey 两个文件没有解析出任何可插入记录,拒绝写库"
            "(避免配合 --replace 清空整表后只插入 0 行)"
        )

    if _targets_real_db(config.database_url) and not config.confirm_real_db:
        raise ConfirmationRequiredError(
            "目标是真实 dietapp.db,必须同时传 --apply --confirm-real-db 才会写入"
        )

    if report.cross_dataset_fdc_id_collisions:
        raise DataAnomalyError(
            "存在跨数据集 fdc_id 冲突(见 report)。fdc_id 是主键,插入时必然真实撞唯一约束,"
            "--allow-anomalies 救不了,必须先核对 Foundation/Survey 两个源文件本身"
        )

    if report.data_type_mismatches and not config.allow_anomalies:
        raise DataAnomalyError(
            "存在 dataType 不一致(见 report),默认拒绝写库;确认无误后加 --allow-anomalies"
        )

    database_url = config.database_url or settings.database_url
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    try:
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            with session.begin():
                existing = session.scalar(select(func.count()).select_from(FoodBaseUs))
                if existing:
                    if not config.replace:
                        raise AlreadyImportedError(
                            f"food_base_us 已有 {existing} 行,加 --replace 才会先清空再插入"
                        )
                    session.execute(delete(FoodBaseUs))
                inserted = insert_food_base_us_records(session, records)
            report.rows_inserted = inserted
        finally:
            session.close()
    finally:
        engine.dispose()

    _maybe_write_report(config, report)
    return report


def _maybe_write_report(config: UsImportConfig, report: UsValidationReport) -> None:
    if config.report_path is not None:
        config.report_path.write_text(report.to_markdown(), encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="导入 food_base_us(USDA FoodData Central Foundation+Survey 批量下载快照)"
    )
    parser.add_argument("--foundation-json", type=Path, default=DEFAULT_FOUNDATION_JSON)
    parser.add_argument("--survey-json", type=Path, default=DEFAULT_SURVEY_JSON)
    parser.add_argument("--database-url", default="")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真的执行写入(不传则只 dry-run,不建数据库连接)",
    )
    parser.add_argument(
        "--confirm-real-db",
        action="store_true",
        help="目标是真实 dietapp.db 时,必须和 --apply 一起传",
    )
    parser.add_argument("--replace", action="store_true", help="表里已有数据时先整表清空再插入")
    parser.add_argument(
        "--allow-anomalies",
        action="store_true",
        help="报告里有 dataType 不一致时,默认拒绝写库,传此参数才会继续执行"
        "(跨数据集 fdc_id 冲突这条永远硬失败,这个参数救不了)",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="校验报告落盘位置(默认写到 food_base_us/import_report.txt,和两个数据集目录平级)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.report_path is not None:
        report_path = args.report_path
    else:
        report_path = _US_BASE_DIR / "import_report.txt"
    config = UsImportConfig(
        foundation_json_path=args.foundation_json,
        survey_json_path=args.survey_json,
        database_url=args.database_url,
        dry_run=not args.apply,
        confirm_real_db=args.confirm_real_db,
        replace=args.replace,
        allow_anomalies=args.allow_anomalies,
        report_path=report_path,
    )

    try:
        report = run_import(config)
    except (
        AlreadyImportedError,
        ConfirmationRequiredError,
        DataAnomalyError,
        EmptySourceError,
    ) as exc:
        print(f"导入未执行:{exc}")
        return 1

    print(report.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
