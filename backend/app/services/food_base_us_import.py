"""解析 USDA FoodData Central 批量下载快照(Foundation+Survey)并整表覆盖写入
food_base_us(SPEC §4.4.2,维护模型见 ADR 0005)。和 food_base_cn_import.py 结构对称。

纯逻辑模块:不打开真实 backend/data/dietapp.db,不做幂等/确认判断——这些防护措施在
backend/scripts/import_food_base_us.py 的 run_import() 里。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.food_base_us import FoodBaseUs
from app.services.usda_adapter import normalize_usda_nutrition

NUTRIENT_FIELDS = ("kcal", "protein", "fat", "carb", "fiber")


@dataclass
class ParsedUsFoodRecord:
    fdc_id: int
    data_type: str
    description: str
    kcal_100g: float | None
    carb_100g: float | None
    protein_100g: float | None
    fat_100g: float | None
    fiber_100g: float | None


@dataclass
class UsValidationReport:
    files_processed: int = 0
    array_entries_total: int = 0
    null_array_entries_skipped: int = 0
    records_parsed: int = 0
    missing_nutrient_counts: dict[str, int] = field(default_factory=dict)
    data_type_mismatches: list[int] = field(default_factory=list)
    cross_dataset_fdc_id_collisions: list[int] = field(default_factory=list)
    rows_inserted: int = 0

    def to_markdown(self) -> str:
        lines = [
            f"- files_processed: {self.files_processed}",
            f"- array_entries_total: {self.array_entries_total}",
            f"- null_array_entries_skipped: {self.null_array_entries_skipped}",
            f"- records_parsed: {self.records_parsed}",
            f"- data_type_mismatches: {len(self.data_type_mismatches)}",
            f"- cross_dataset_fdc_id_collisions: {len(self.cross_dataset_fdc_id_collisions)}",
            f"- rows_inserted: {self.rows_inserted}",
            "",
            "### missing_nutrient_counts",
        ]
        for field_name in NUTRIENT_FIELDS:
            count = self.missing_nutrient_counts.get(field_name, 0)
            lines.append(f"- {field_name}: {count}")
        return "\n".join(lines)


def parse_us_food_base_file(
    path: Path, *, expected_data_type: str
) -> tuple[list[ParsedUsFoodRecord], UsValidationReport]:
    """读取**一个**下载文件,跳过数组里的字面 JSON null,对每条真实食物对象调用
    usda_adapter.normalize_usda_nutrition 提取 5 项营养;同时校验每条记录的 dataType
    字段是否等于 expected_data_type,不等的 fdc_id 计入 report.data_type_mismatches
    (不因此丢弃这条记录,是否要因此拒绝整批导入由调用方决定)。这里返回的
    report.cross_dataset_fdc_id_collisions 恒为空列表——单文件函数看不到另一个文件的
    fdc_id,真正的跨数据集冲突检测在 import_food_base_us_snapshot 里做。
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    array = next(iter(data.values()))

    report = UsValidationReport(files_processed=1, array_entries_total=len(array))
    records: list[ParsedUsFoodRecord] = []

    for raw in array:
        if raw is None:
            report.null_array_entries_skipped += 1
            continue

        fdc_id = raw["fdcId"]
        data_type = raw["dataType"]
        if data_type != expected_data_type:
            report.data_type_mismatches.append(fdc_id)

        nutrition = normalize_usda_nutrition(raw)
        for field_name, value in (
            ("kcal", nutrition.kcal_100g),
            ("protein", nutrition.protein_100g),
            ("fat", nutrition.fat_100g),
            ("carb", nutrition.carb_100g),
            ("fiber", nutrition.fiber_100g),
        ):
            if value is None:
                report.missing_nutrient_counts[field_name] = (
                    report.missing_nutrient_counts.get(field_name, 0) + 1
                )

        records.append(
            ParsedUsFoodRecord(
                fdc_id=fdc_id,
                data_type=data_type,
                description=raw["description"],
                kcal_100g=nutrition.kcal_100g,
                carb_100g=nutrition.carb_100g,
                protein_100g=nutrition.protein_100g,
                fat_100g=nutrition.fat_100g,
                fiber_100g=nutrition.fiber_100g,
            )
        )

    report.records_parsed = len(records)
    return records, report


def import_food_base_us_snapshot(
    foundation_path: Path, survey_path: Path
) -> tuple[list[ParsedUsFoodRecord], UsValidationReport]:
    """Foundation + Survey 两个文件的协调入口——CLI 只应该调用这一个函数,不要自己
    分别调两次 parse_us_food_base_file 再手动拼报告。这一步不碰数据库。"""
    foundation_records, foundation_report = parse_us_food_base_file(
        foundation_path, expected_data_type="Foundation"
    )
    survey_records, survey_report = parse_us_food_base_file(
        survey_path, expected_data_type="Survey (FNDDS)"
    )

    merged_report = UsValidationReport(
        files_processed=foundation_report.files_processed + survey_report.files_processed,
        array_entries_total=foundation_report.array_entries_total
        + survey_report.array_entries_total,
        null_array_entries_skipped=foundation_report.null_array_entries_skipped
        + survey_report.null_array_entries_skipped,
        records_parsed=foundation_report.records_parsed + survey_report.records_parsed,
        data_type_mismatches=foundation_report.data_type_mismatches
        + survey_report.data_type_mismatches,
    )
    for field_name in NUTRIENT_FIELDS:
        foundation_missing = foundation_report.missing_nutrient_counts.get(field_name, 0)
        survey_missing = survey_report.missing_nutrient_counts.get(field_name, 0)
        merged_report.missing_nutrient_counts[field_name] = foundation_missing + survey_missing

    foundation_ids = {r.fdc_id for r in foundation_records}
    survey_ids = {r.fdc_id for r in survey_records}
    merged_report.cross_dataset_fdc_id_collisions = sorted(foundation_ids & survey_ids)

    return foundation_records + survey_records, merged_report


def insert_food_base_us_records(
    session: Session, records: list[ParsedUsFoodRecord], *, batch_size: int = 500
) -> int:
    """只负责"给它记录就插",和 insert_food_base_cn_records 同样的分工:不管幂等、
    不 commit。不用 fdc_id 做 get-or-create:表内容是当前锁定版本的整体重建结果,
    不是可以按主键增量合并的缓存(维护模型见 ADR 0005)。created_at 显式写入 UTC 时间,
    和 insert_food_base_cn_records 的写法相同。"""
    created_at = datetime.now(timezone.utc).isoformat()
    inserted = 0
    batch: list[FoodBaseUs] = []

    for record in records:
        batch.append(
            FoodBaseUs(
                fdc_id=record.fdc_id,
                data_type=record.data_type,
                description=record.description,
                kcal_100g=record.kcal_100g,
                carb_100g=record.carb_100g,
                protein_100g=record.protein_100g,
                fat_100g=record.fat_100g,
                fiber_100g=record.fiber_100g,
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
