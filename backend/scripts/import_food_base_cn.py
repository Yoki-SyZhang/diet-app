"""food_base_cn 导入 CLI(SPEC §4.4.1,维护模型见 ADR 0005)。

唯一能打开真实 backend/data/dietapp.db 的入口:默认 dry-run,只解析+校验+打印报告,
不建任何数据库连接;--apply --confirm-real-db 两个参数同时传才会真的写真实库。
业务判断都在 run_import() 这个纯函数里,不摸 argparse,方便单测直接构造不同的
ImportConfig 组合调用;main() 只做参数解析和输出格式化。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.models.food_base_cn import FoodBaseCn
from app.services.food_base_cn_import import (
    ValidationReport,
    insert_food_base_cn_records,
    parse_food_base_cn_directory,
)
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

DEFAULT_SOURCE_COMMIT = "095034a96376d893582b412900fa8fdf792b4194"
DEFAULT_SOURCE_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "food_base"
    / "food_base_cn"
    / "json_data_vision_251206_Qwen2-5-VL-72B-Instruct"
)


class AlreadyImportedError(Exception):
    """food_base_cn 表里已有任何行(不论来自哪个 source_commit)且未传 --replace。"""


class ConfirmationRequiredError(Exception):
    """非 dry-run 且指向真实 dietapp.db 但未传 --confirm-real-db。"""


class DataAnomalyError(Exception):
    """report.duplicate_food_codes 或 report.edible_out_of_range 非空且未传 --allow-anomalies。"""


class EmptySourceError(Exception):
    """source_dir 下没有解析出任何可插入记录——多半是路径配错,不能配合 --replace
    先清空整表再插入 0 行。不受 --allow-anomalies 影响,永远硬失败。"""


@dataclass
class ImportConfig:
    source_dir: Path = DEFAULT_SOURCE_DIR
    source_commit: str = DEFAULT_SOURCE_COMMIT
    database_url: str = ""  # 空字符串代表用 settings.database_url(即真实文件)
    dry_run: bool = True
    confirm_real_db: bool = False
    replace: bool = False
    allow_anomalies: bool = False
    report_path: Path | None = None  # None = 不落盘,只有 main() 会给出默认路径


def _targets_real_db(database_url: str) -> bool:
    """判断(不论是留空走默认、还是显式传入)最终解析出的数据库地址是不是真实
    dietapp.db——按实际 sqlite 文件路径比较,而不是只看 database_url 是不是空字符串,
    否则显式传入和默认值完全相同的真实路径就能绕过 --confirm-real-db 检查。"""
    resolved = database_url or settings.database_url
    real = settings.database_url
    resolved_url = make_url(resolved)
    real_url = make_url(real)
    if not resolved_url.drivername.startswith("sqlite") or not real_url.drivername.startswith(
        "sqlite"
    ):
        return resolved == real
    if not resolved_url.database or not real_url.database:
        return resolved == real  # 例如 sqlite:///:memory: 没有真实文件路径可比较
    return Path(resolved_url.database).resolve() == Path(real_url.database).resolve()


def run_import(config: ImportConfig) -> ValidationReport:
    """
    - dry_run=True(默认):只跑 parse_food_base_cn_directory,不创建任何数据库连接。
      报告照常生成、如实展示重复编码/越界可食率,不因为将来可能被拒绝就不统计。
    - dry_run=False 且指向真实 dietapp.db(按实际 sqlite 文件路径比较,不只看 database_url
      是不是空字符串)且 confirm_real_db=False:抛 ConfirmationRequiredError,同样不打开连接。
    - dry_run=False 且没有解析出任何可插入记录:抛 EmptySourceError,不写库——避免
      source_dir 配错时配合 --replace 把整表清空又插入 0 行。
    - dry_run=False 且(report.duplicate_food_codes 或 report.edible_out_of_range 非空)且
      allow_anomalies=False:抛 DataAnomalyError,不写库。
    - dry_run=False 且表里已有任何行(不论是不是同一个 source_commit)且 replace=False:
      抛 AlreadyImportedError。
    - dry_run=False 且 replace=True:删+插在同一个显式事务里,任何一步异常整体回滚。
    """
    records, report = parse_food_base_cn_directory(
        config.source_dir, source_commit=config.source_commit
    )

    if config.dry_run:
        _maybe_write_report(config, report)
        return report

    if not records:
        raise EmptySourceError(
            f"{config.source_dir} 下没有解析出任何可插入记录,拒绝写库"
            "(避免配合 --replace 清空整表后只插入 0 行)"
        )

    if _targets_real_db(config.database_url) and not config.confirm_real_db:
        raise ConfirmationRequiredError(
            "目标是真实 dietapp.db,必须同时传 --apply --confirm-real-db 才会写入"
        )

    if (report.duplicate_food_codes or report.edible_out_of_range) and not config.allow_anomalies:
        raise DataAnomalyError(
            "存在重复编码或可食率越界(见 report),默认拒绝写库;确认无误后加 --allow-anomalies"
        )

    database_url = config.database_url or settings.database_url
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    try:
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            with session.begin():
                existing = session.scalar(select(func.count()).select_from(FoodBaseCn))
                if existing:
                    if not config.replace:
                        raise AlreadyImportedError(
                            f"food_base_cn 已有 {existing} 行,加 --replace 才会先清空再插入"
                        )
                    session.execute(delete(FoodBaseCn))
                inserted = insert_food_base_cn_records(session, records)
            report.rows_inserted = inserted
        finally:
            session.close()
    finally:
        engine.dispose()

    _maybe_write_report(config, report)
    return report


def _maybe_write_report(config: ImportConfig, report: ValidationReport) -> None:
    if config.report_path is not None:
        config.report_path.write_text(report.to_markdown(), encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入 food_base_cn(中国食物成分表 OCR 快照)")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--source-commit", default=DEFAULT_SOURCE_COMMIT)
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
        help="报告里有重复编码/越界可食率时,默认拒绝写库,传此参数才会按既有规则继续执行",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="校验报告落盘位置(默认写到 source-dir 下的 import_report.txt,和 MANIFEST.txt 放一起)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    report_path = (
        args.report_path if args.report_path is not None else args.source_dir / "import_report.txt"
    )
    config = ImportConfig(
        source_dir=args.source_dir,
        source_commit=args.source_commit,
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
