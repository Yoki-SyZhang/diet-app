"""1.9 餐次明细路由。POST 幂等(重复 confirmation_id 也返回 201,内容是已有记录);
DELETE 天然幂等(重复删不存在的 id 就是 404)。业务规则在 `services/meal_entry_write.py`。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.meal_entry import ConfirmMealEntryRequest, MealEntryOut
from app.services.meal_entry_write import (
    UntrustedNutritionError,
    confirm_meal_entry,
    delete_todays_meal_entry,
    list_today_meal_entries,
)

router = APIRouter(prefix="/meal-entries", tags=["meal-entries"])


@router.post("", response_model=MealEntryOut, status_code=status.HTTP_201_CREATED)
def post_meal_entry(
    payload: ConfirmMealEntryRequest, db: Session = Depends(get_db)
) -> MealEntryOut:
    try:
        entry = confirm_meal_entry(
            db, payload.preview, payload.confirmation_id, now_utc=payload.now_utc
        )
    except UntrustedNutritionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MealEntryOut.model_validate(entry)


@router.get("/today", response_model=list[MealEntryOut])
def get_today_entries(db: Session = Depends(get_db)) -> list[MealEntryOut]:
    return [MealEntryOut.model_validate(e) for e in list_today_meal_entries(db)]


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal_entry(entry_id: int, db: Session = Depends(get_db)) -> None:
    if not delete_todays_meal_entry(db, entry_id):
        raise HTTPException(status_code=404, detail="记录不存在或不属于今日")
