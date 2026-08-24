"""1.9 对话路由。Router 只做请求→服务函数→响应模型转换,业务规则全部在
`services/chat_turn.py`(AGENTS.md:API 层只负责边界转换)。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_llm_client
from app.schemas.chat import (
    ChatMessageIn,
    ChatMessageOut,
    ChatTurnResponse,
    ModifyCorrectionRequest,
    ModifyCorrectionResponse,
    OpenBatchOut,
    RecapRequest,
    RecapResponse,
)
from app.services.chat import list_today_chat_messages
from app.services.chat_turn import (
    find_open_batch,
    handle_modify_correction,
    handle_new_message,
    recap_batch_status,
)
from app.services.llm_client import LlmClient

router = APIRouter(prefix="/chat/messages", tags=["chat"])


@router.post("", response_model=ChatTurnResponse)
async def post_message(
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
    client: LlmClient = Depends(get_llm_client),
) -> ChatTurnResponse:
    result = await handle_new_message(db, client, payload.text)
    return ChatTurnResponse(
        user_message=ChatMessageOut.model_validate(result.user_message),
        assistant_message=ChatMessageOut.model_validate(result.assistant_message),
        intent=result.intent,
        outcome=result.outcome,
        batch_id=result.batch_id,
        items=result.items,
    )


@router.post("/modify", response_model=ModifyCorrectionResponse)
async def post_modify(
    payload: ModifyCorrectionRequest,
    db: Session = Depends(get_db),
    client: LlmClient = Depends(get_llm_client),
) -> ModifyCorrectionResponse:
    result = await handle_modify_correction(
        db,
        client,
        payload.original_item,
        payload.meal_slot,
        payload.correction_text,
        payload.confirmation_id,
    )
    return ModifyCorrectionResponse(
        confirmation_id=result.confirmation_id,
        success=result.success,
        outcome=result.outcome,
        failure_reason=result.failure_reason,
    )


@router.post("/recap", response_model=RecapResponse)
async def post_recap(
    payload: RecapRequest,
    db: Session = Depends(get_db),
    client: LlmClient = Depends(get_llm_client),
) -> RecapResponse:
    message = await recap_batch_status(
        db,
        client,
        payload.batch_id,
        payload.meal_slot,
        payload.items,
        now_utc=payload.now_utc,
    )
    return RecapResponse(assistant_message=ChatMessageOut.model_validate(message))


@router.get("/today", response_model=list[ChatMessageOut])
def get_today_messages(db: Session = Depends(get_db)) -> list[ChatMessageOut]:
    return [
        ChatMessageOut.model_validate(m) for m in list_today_chat_messages(db)
    ]


@router.get("/open-batch", response_model=OpenBatchOut | None)
def get_open_batch(db: Session = Depends(get_db)) -> OpenBatchOut | None:
    open_batch = find_open_batch(db)
    if open_batch is None:
        return None
    return OpenBatchOut(batch_id=open_batch.batch_id, items=open_batch.items)
