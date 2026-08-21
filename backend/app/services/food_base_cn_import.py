"""解析中国食物成分表 OCR 快照并整表覆盖写入 food_base_cn(SPEC §4.4.1,维护模型见 ADR 0005)。

纯逻辑模块:不打开真实 backend/data/dietapp.db,不做幂等/确认判断——这些防护措施在
backend/scripts/import_food_base_cn.py 的 run_import() 里,方便脱离真实库单测。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.food_base_cn import FoodBaseCn

TARGET_FIELDS = ("edible", "energyKCal", "protein", "fat", "CHO", "dietaryFiber")

_DASH = "—"  # 中国食物成分表用的破折号(em dash),不是 ASCII 连字符


def coerce_nutrient_value(raw: str | None) -> tuple[float | None, str]:
    """status 六选一:'ok' | 'footnote_calculated'(去掉尾部 * 后解析成功)
    | 'dirty_empty' | 'dirty_trace'(Tr) | 'dirty_dash'(——) | 'dirty_unrecognized'(如 'un')

    返回值语义:
    - 'ok' / 'footnote_calculated' 两种 -> 返回 (解析出的数字, status)。'footnote_calculated'
      不是脏值,是"去掉星号后能拿到真实数字"的合法数据,数字本身照常参与计算、照常入库,只是
      status 标记这个数字来自脚注换算、不是原始测量值。
    - 'dirty_empty' / 'dirty_trace' / 'dirty_dash' / 'dirty_unrecognized' 四种 -> 返回
      (None, status)。只有这四种才是真正没有可用数值。
    - 输入字符串是 "0" 这种合法的零值 -> status='ok',返回 (0.0, 'ok'),不当缺失处理。
    """
    if raw is None:
        return None, "dirty_empty"
    text = raw.strip()
    if text == "":
        return None, "dirty_empty"
    if text == "Tr":
        return None, "dirty_trace"
    if text == _DASH:
        return None, "dirty_dash"
    if text.endswith("*"):
        body = text[:-1]
        try:
            return float(body), "footnote_calculated"
        except ValueError:
            return None, "dirty_unrecognized"
    try:
        return float(text), "ok"
    except ValueError:
        return None, "dirty_unrecognized"


@dataclass
class ParsedFoodRecord:
    food_code: str
    food_name: str
    edible_pct: float | None
    kcal_100g: float | None
    carb_100g: float | None
    protein_100g: float | None
    fat_100g: float | None
    fiber_100g: float | None
    source_commit: str
    source_file: str  # 仅用于去重报告追溯,不写入数据库


@dataclass
class ValidationReport:
    files_processed: int = 0
    records_parsed: int = 0
    dirty_value_counts: dict[str, Counter[str]] = field(default_factory=dict)
    duplicate_food_codes: dict[str, list[str]] = field(default_factory=dict)
    fully_null_records: list[tuple[str, str]] = field(default_factory=list)
    unrecognized_values: list[tuple[str, str, str, str]] = field(default_factory=list)
    edible_out_of_range: list[tuple[str, float]] = field(default_factory=list)
    rows_inserted: int = 0

    def to_markdown(self) -> str:
        lines = [
            f"- files_processed: {self.files_processed}",
            f"- records_parsed: {self.records_parsed}",
            f"- duplicate_food_codes: {len(self.duplicate_food_codes)}",
            f"- fully_null_records: {len(self.fully_null_records)}",
            f"- unrecognized_values: {len(self.unrecognized_values)}",
            f"- edible_out_of_range: {len(self.edible_out_of_range)}",
            f"- rows_inserted: {self.rows_inserted}",
            "",
            "### dirty_value_counts",
        ]
        for field_name, counter in self.dirty_value_counts.items():
            if counter:
                detail = ", ".join(f"{status}={count}" for status, count in sorted(counter.items()))
                lines.append(f"- {field_name}: {detail}")
        return "\n".join(lines)


def parse_record(
    raw: dict, *, source_commit: str, source_file: str, report: ValidationReport
) -> ParsedFoodRecord:
    food_code = raw["foodCode"]
    food_name = raw["foodName"]

    values: dict[str, float | None] = {}
    for field_name in TARGET_FIELDS:
        value, status = coerce_nutrient_value(raw.get(field_name))
        report.dirty_value_counts.setdefault(field_name, Counter())[status] += 1
        if status == "dirty_unrecognized":
            report.unrecognized_values.append(
                (source_file, food_code, field_name, str(raw.get(field_name)))
            )
        values[field_name] = value

    edible_pct = values["edible"]
    if edible_pct is not None and not (0 < edible_pct <= 100):
        report.edible_out_of_range.append((food_code, edible_pct))

    return ParsedFoodRecord(
        food_code=food_code,
        food_name=food_name,
        edible_pct=edible_pct,
        kcal_100g=values["energyKCal"],
        carb_100g=values["CHO"],
        protein_100g=values["protein"],
        fat_100g=values["fat"],
        fiber_100g=values["dietaryFiber"],
        source_commit=source_commit,
        source_file=source_file,
    )


def dedupe_by_food_code(
    records: list[ParsedFoodRecord], report: ValidationReport
) -> list[ParsedFoodRecord]:
    """按 food_code 去重:保留排序后第一次出现的那条,后面的丢弃并计入
    report.duplicate_food_codes(food_code -> 出现过的全部 source_file 列表)。"""
    files_by_code: dict[str, list[str]] = {}
    for record in records:
        files_by_code.setdefault(record.food_code, []).append(record.source_file)

    kept_codes: set[str] = set()
    result: list[ParsedFoodRecord] = []
    for record in records:
        if record.food_code in kept_codes:
            continue
        kept_codes.add(record.food_code)
        result.append(record)

    for food_code, files in files_by_code.items():
        if len(files) > 1:
            report.duplicate_food_codes[food_code] = files

    return result


def filter_fully_null_records(
    records: list[ParsedFoodRecord], report: ValidationReport
) -> list[ParsedFoodRecord]:
    """排除 edible_pct 和 5 项营养字段全部为 None 的记录(如 192011/麻子籽这种整条
    OCR 不出任何数值的记录)。food_code/food_name 恒有值,不参与这个判断。
    排除的记录计入 report.fully_null_records,不进入返回列表。"""
    result: list[ParsedFoodRecord] = []
    for record in records:
        if (
            record.edible_pct is None
            and record.kcal_100g is None
            and record.carb_100g is None
            and record.protein_100g is None
            and record.fat_100g is None
            and record.fiber_100g is None
        ):
            report.fully_null_records.append((record.food_code, record.food_name))
            continue
        result.append(record)
    return result


def parse_food_base_cn_directory(
    directory: Path, *, source_commit: str
) -> tuple[list[ParsedFoodRecord], ValidationReport]:
    """逐文件解析 -> 去重 -> 过滤全空记录,返回待插入列表 + report。"""
    report = ValidationReport()
    all_records: list[ParsedFoodRecord] = []

    for file_path in sorted(directory.glob("merged_*.json")):
        report.files_processed += 1
        raw_records = json.loads(file_path.read_text(encoding="utf-8"))
        for raw in raw_records:
            all_records.append(
                parse_record(
                    raw,
                    source_commit=source_commit,
                    source_file=file_path.name,
                    report=report,
                )
            )

    report.records_parsed = len(all_records)
    deduped = dedupe_by_food_code(all_records, report)
    filtered = filter_fully_null_records(deduped, report)
    return filtered, report


def insert_food_base_cn_records(
    session: Session, records: list[ParsedFoodRecord], *, batch_size: int = 500
) -> int:
    """只负责"给它记录就插",不管幂等、不 commit——事务边界交给调用方。
    每条插入的 created_at 显式写入 UTC 时间,和项目"时间戳一律 UTC-0 存储"的铁律一致。"""
    created_at = datetime.now(timezone.utc).isoformat()
    inserted = 0
    batch: list[FoodBaseCn] = []

    for record in records:
        batch.append(
            FoodBaseCn(
                food_code=record.food_code,
                food_name=record.food_name,
                edible_pct=record.edible_pct,
                kcal_100g=record.kcal_100g,
                carb_100g=record.carb_100g,
                protein_100g=record.protein_100g,
                fat_100g=record.fat_100g,
                fiber_100g=record.fiber_100g,
                source_commit=record.source_commit,
                created_at=created_at,
            )
        )
        if len(batch) >= batch_size:
            session.add_all(batch)
            session.flush()
            inserted += len(batch)
            batch = []

    if batch:
        session.add_all(batch)
        session.flush()
        inserted += len(batch)

    return inserted
