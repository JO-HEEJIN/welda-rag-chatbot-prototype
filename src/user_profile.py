"""User profile model used to personalize the Welda RAG chatbot."""

from typing import Literal

from pydantic import BaseModel, Field

GENDER_KOR = {"male": "남성", "female": "여성", "other": "기타"}

INSULIN_LEVEL_KOR = {"low": "낮음", "moderate": "보통", "high": "높음"}

DIET_GOAL_KOR = {
    "weight_loss": "체중 감량",
    "blood_sugar_control": "혈당 관리 중심 다이어트",
    "muscle_gain": "근육 증가",
    "maintenance": "현 상태 유지",
}

CONDITION_KOR = {
    "diabetes_type1": "제1형 당뇨병",
    "diabetes_type2": "제2형 당뇨병",
    "hypertension": "고혈압",
    "hyperlipidemia": "고지혈증",
    "obesity": "비만",
    "fatty_liver": "지방간",
}

RESTRICTION_KOR = {
    "vegetarian": "채식주의",
    "vegan": "비건",
    "lactose_intolerant": "유당불내증",
    "gluten_free": "글루텐 프리",
    "halal": "할랄",
    "kosher": "코셔",
    "pescatarian": "페스코",
}


class UserProfile(BaseModel):
    """Structured profile that the RAG prompt can use for personalization.

    Validation enforces realistic ranges so an obviously bad input (negative age,
    glucose of 5 or 5000) never reaches the LLM prompt.
    """

    age: int = Field(ge=1, le=120)
    gender: Literal["male", "female", "other"]
    insulin_resistance_level: Literal["low", "moderate", "high"] = "moderate"
    avg_fasting_glucose: float | None = Field(default=None, ge=50, le=300)
    diet_goal: Literal[
        "weight_loss", "blood_sugar_control", "muscle_gain", "maintenance"
    ]
    medical_conditions: list[str] = []
    dietary_restrictions: list[str] = []

    def to_prompt_context(self) -> str:
        """Render the profile as one Korean sentence for prompt injection."""
        parts = [f"{self.age}세 {GENDER_KOR[self.gender]}"]
        parts.append(f"인슐린 저항성 {INSULIN_LEVEL_KOR[self.insulin_resistance_level]}")
        if self.avg_fasting_glucose is not None:
            parts.append(f"평균 공복혈당 {self.avg_fasting_glucose:g} mg/dL")
        parts.append(f"목표는 {DIET_GOAL_KOR[self.diet_goal]}")

        conditions = [CONDITION_KOR.get(c, c) for c in self.medical_conditions] or ["없음"]
        parts.append(f"만성질환: {', '.join(conditions)}")

        restrictions = [RESTRICTION_KOR.get(r, r) for r in self.dietary_restrictions] or ["없음"]
        parts.append(f"식이제한: {', '.join(restrictions)}")

        return ", ".join(parts)
