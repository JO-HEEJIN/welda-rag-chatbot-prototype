"""Tests for the UserProfile model and to_prompt_context()."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.user_profile import UserProfile


def test_normal_profile_creation() -> None:
    profile = UserProfile(
        age=32,
        gender="female",
        insulin_resistance_level="moderate",
        avg_fasting_glucose=105.0,
        diet_goal="blood_sugar_control",
        medical_conditions=[],
        dietary_restrictions=["lactose_intolerant"],
    )
    assert profile.age == 32
    assert profile.gender == "female"
    assert profile.dietary_restrictions == ["lactose_intolerant"]


def test_invalid_age_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        UserProfile(age=0, gender="female", diet_goal="maintenance")
    with pytest.raises(ValidationError):
        UserProfile(age=200, gender="female", diet_goal="maintenance")


def test_invalid_glucose_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        UserProfile(
            age=30,
            gender="male",
            avg_fasting_glucose=10.0,
            diet_goal="maintenance",
        )
    with pytest.raises(ValidationError):
        UserProfile(
            age=30,
            gender="male",
            avg_fasting_glucose=500.0,
            diet_goal="maintenance",
        )


def test_to_prompt_context_format() -> None:
    profile = UserProfile(
        age=32,
        gender="female",
        insulin_resistance_level="moderate",
        avg_fasting_glucose=105.0,
        diet_goal="blood_sugar_control",
        medical_conditions=[],
        dietary_restrictions=["lactose_intolerant"],
    )
    context = profile.to_prompt_context()
    assert "32세 여성" in context
    assert "인슐린 저항성 보통" in context
    assert "평균 공복혈당 105 mg/dL" in context
    assert "혈당 관리 중심 다이어트" in context
    assert "만성질환: 없음" in context
    assert "식이제한: 유당불내증" in context


def test_to_prompt_context_with_no_glucose() -> None:
    profile = UserProfile(
        age=45,
        gender="male",
        diet_goal="weight_loss",
        medical_conditions=["diabetes_type2"],
    )
    context = profile.to_prompt_context()
    assert "공복혈당" not in context
    assert "제2형 당뇨병" in context
    assert "식이제한: 없음" in context
