"""1.8 自然语言解析的真实评测(tasks/current.md)。不是 pytest 用例,手动运行:

    conda activate vibe-coding
    cd backend
    python -m scripts.eval_nl_parse

需要 `backend/.env` 配好 `DASHSCOPE_API_KEY`。读取
`tests/backend/eval/food_text_parse_dataset.csv`,对每一行真实调用 `parse_diet_text`,
分别统计:

- 首次结构合法率:第一次模型响应就满足 nl_parse 契约的比例;
- 最终结构合法率(自动重试后):对应 SPEC §11.1"文本解析合法结构率 ≥95%"这条门槛;
- 语义准确率:resolved/needs_clarification 判断是否匹配数据集标注的 expected_outcome
  (质量参考,SPEC 没有单独定数字门槛)。

`service_unavailable`(网络/超时/限流,infra 抖动不是模型质量问题)单独计数,不进上述
比率的分母。失败/不合格样本连同原始响应存到
`tests/backend/eval/results/<timestamp>_nl_parse.json`。
"""

from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from app.schemas.llm_outcome import LlmOutcome
from app.services import nl_parse
from app.services.llm_client import LlmClient, LlmJsonResult, create_dashscope_client

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = REPO_ROOT / "tests" / "backend" / "eval" / "food_text_parse_dataset.csv"
RESULTS_DIR = REPO_ROOT / "tests" / "backend" / "eval" / "results"

_RESOLVED = LlmOutcome.RESOLVED.value
_NEEDS_CLARIFICATION = LlmOutcome.NEEDS_CLARIFICATION.value
_INVALID_MODEL_OUTPUT = LlmOutcome.INVALID_MODEL_OUTPUT.value


@dataclass
class RowRecord:
    id: str
    category: str
    input_text: str
    expected_outcome: str
    attempts: list[str] = field(default_factory=list)  # "legal" | "illegal" | "network_failure"
    final_outcome: str | None = None
    final_message: str | None = None
    error: str | None = None


class _RecordingClient:
    """包一层真实 client,记录每次 chat_json 调用的原始响应是否满足 nl_parse 的契约。

    不改动 nl_parse.py 本身——生产代码不需要知道自己正在被评测,重试逻辑仍然完全由
    parse_diet_text 内部驱动,这里只是旁观记录每次尝试的结果。
    """

    def __init__(self, inner: LlmClient, record: RowRecord) -> None:
        self._inner = inner
        self._record = record

    async def chat_json(
        self, *, system: str, user: str, temperature: float = 0.0
    ) -> LlmJsonResult:
        result = await self._inner.chat_json(system=system, user=user, temperature=temperature)
        if not result.ok:
            if result.error_kind == "response_not_json":
                self._record.attempts.append("illegal")
            else:
                self._record.attempts.append("network_failure")
            return result

        try:
            nl_parse._build_result(result.parsed)
            self._record.attempts.append("legal")
        except Exception:
            self._record.attempts.append("illegal")
        return result


def _is_service_unavailable(record: RowRecord) -> bool:
    return bool(record.error) or "network_failure" in record.attempts


async def _run_one(client: LlmClient, row: dict) -> RowRecord:
    record = RowRecord(
        id=row["id"],
        category=row["category"],
        input_text=row["input_text"],
        expected_outcome=row["expected_outcome"],
    )
    recording_client = _RecordingClient(client, record)
    try:
        result = await nl_parse.parse_diet_text(recording_client, row["input_text"])
        record.final_outcome = result.outcome.value
        record.final_message = result.message
    except Exception as exc:  # 评测脚本要能跑完整批,单条崩溃不能中断整体
        record.error = f"{type(exc).__name__}: {exc}"
    return record


def _load_dataset() -> list[dict]:
    with DATASET_PATH.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _summarize(records: list[RowRecord]) -> dict:
    service_unavailable = [r for r in records if _is_service_unavailable(r)]
    scoreable = [r for r in records if not _is_service_unavailable(r)]
    n = len(scoreable)

    first_legal = sum(1 for r in scoreable if r.attempts and r.attempts[0] == "legal")
    final_legal = sum(
        1 for r in scoreable if r.final_outcome in (_RESOLVED, _NEEDS_CLARIFICATION)
    )
    semantic_scoreable = [
        r for r in scoreable if r.final_outcome in (_RESOLVED, _NEEDS_CLARIFICATION)
    ]
    semantic_correct = sum(
        1 for r in semantic_scoreable if r.final_outcome == r.expected_outcome
    )

    return {
        "total_rows": len(records),
        "service_unavailable_count": len(service_unavailable),
        "scoreable_rows": n,
        "first_attempt_legal_rate": (first_legal / n) if n else None,
        "final_legal_rate": (final_legal / n) if n else None,
        "semantic_scoreable_rows": len(semantic_scoreable),
        "semantic_accuracy": (
            (semantic_correct / len(semantic_scoreable)) if semantic_scoreable else None
        ),
    }


def _fmt_pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "N/A"


async def main() -> None:
    dataset = _load_dataset()
    async with httpx.AsyncClient() as http_client:
        client = create_dashscope_client(http_client)
        records = list(await asyncio.gather(*(_run_one(client, row) for row in dataset)))

    summary = _summarize(records)

    print(f"总样本数: {summary['total_rows']}")
    print(f"service_unavailable(排除出分母): {summary['service_unavailable_count']}")
    print(f"参与结构合法率统计的样本数: {summary['scoreable_rows']}")
    print(f"首次结构合法率: {_fmt_pct(summary['first_attempt_legal_rate'])}")
    print(f"最终结构合法率(对应 SPEC §11.1 95% 门槛): {_fmt_pct(summary['final_legal_rate'])}")
    print(
        f"语义准确率(参考,非硬性门槛,基于 {summary['semantic_scoreable_rows']} 条): "
        f"{_fmt_pct(summary['semantic_accuracy'])}"
    )

    failures = [
        r
        for r in records
        if _is_service_unavailable(r)
        or r.final_outcome == _INVALID_MODEL_OUTPUT
        or (
            r.final_outcome in (_RESOLVED, _NEEDS_CLARIFICATION)
            and r.final_outcome != r.expected_outcome
        )
    ]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{timestamp}_nl_parse.json"
    out_path.write_text(
        json.dumps(
            {
                "summary": summary,
                "failures": [
                    {
                        "id": r.id,
                        "category": r.category,
                        "input_text": r.input_text,
                        "expected_outcome": r.expected_outcome,
                        "final_outcome": r.final_outcome,
                        "final_message": r.final_message,
                        "attempts": r.attempts,
                        "error": r.error,
                    }
                    for r in failures
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"结果已存到: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
