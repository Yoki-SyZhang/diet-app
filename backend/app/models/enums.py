from typing import Literal

MEAL_SLOT_VALUES = ("breakfast", "lunch", "dinner", "other")
MealSlot = Literal["breakfast", "lunch", "dinner", "other"]

UNIT_VALUES = ("g", "serving")
Unit = Literal["g", "serving"]

SOURCE_TAG_VALUES = ("chn_table", "usda", "decompose_estimate", "llm_estimate", "user_create")
SourceTag = Literal["chn_table", "usda", "decompose_estimate", "llm_estimate", "user_create"]
