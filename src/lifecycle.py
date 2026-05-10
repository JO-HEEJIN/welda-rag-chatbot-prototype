"""Welda's 5-stage user lifecycle model used by the LangGraph state machine.

Each stage carries metadata that shapes the coaching prompt: focus areas,
tone guideline, and explicitly prohibited topics. A user in UNDERSTANDING
should not be pushed toward fat-loss tactics, while a user in FAT_BURN
expects concrete, action-oriented advice rather than introductory framing.
"""

from dataclasses import dataclass, field
from enum import Enum


class LifecycleStage(str, Enum):
    """Five sequential stages of the Welda glucose-coaching journey."""

    UNDERSTANDING = "understanding"
    SPIKE_CONTROL = "spike_control"
    HUNGER_CONTROL = "hunger_control"
    FAT_BURN = "fat_burn"
    MAINTENANCE = "maintenance"


@dataclass(frozen=True)
class LifecycleMeta:
    """Per-stage metadata injected into the coaching prompt."""

    description: str
    focus_areas: list[str] = field(default_factory=list)
    tone_guideline: str = ""
    prohibited_topics: list[str] = field(default_factory=list)


LIFECYCLE_METADATA: dict[LifecycleStage, LifecycleMeta] = {
    LifecycleStage.UNDERSTANDING: LifecycleMeta(
        description="내 몸 이해하기 — 웰다 시작 직후, 자신의 혈당 반응과 생활 패턴을 관찰하는 단계",
        focus_areas=[
            "혈당의 기본 개념과 변동의 의미",
            "CGM(연속혈당측정) 데이터 읽는 법",
            "본인 식습관과 생활 패턴 자가 관찰",
            "혈당 스파이크의 원인 인식",
        ],
        tone_guideline="교육적이고 격려하는 톤. 사용자가 자기 몸의 신호를 처음 읽기 시작하는 단계이므로, 지식 전달과 정서적 안정을 동시에 제공",
        prohibited_topics=[
            "체지방 감량 압박",
            "엄격한 식단 제한 강요",
            "단식 또는 극단적 칼로리 제한",
            "고강도 운동 처방",
        ],
    ),
    LifecycleStage.SPIKE_CONTROL: LifecycleMeta(
        description="혈당 스파이크 조절 — 평소 생활패턴 파악 후 식후 혈당 급상승을 줄이는 단계",
        focus_areas=[
            "GI/GL 이해와 활용",
            "식사 순서 (채소-단백질-탄수화물)",
            "탄수화물 종류와 정제도",
            "식후 가벼운 활동의 효과",
            "식초/시나몬 등 보조 전략",
        ],
        tone_guideline="구체적이고 실용적인 톤. 식사 단위의 즉시 적용 가능한 팁을 제공하되, 완벽주의가 아닌 점진적 개선을 강조",
        prohibited_topics=[
            "체지방 감량 강요",
            "단식 권유",
            "하루 칼로리 총량 통제",
        ],
    ),
    LifecycleStage.HUNGER_CONTROL: LifecycleMeta(
        description="배고픔 조절 — 스파이크가 줄어 증상이 개선되며, 가짜 배고픔을 식별하고 식욕을 안정화하는 단계",
        focus_areas=[
            "진짜 배고픔과 가짜 배고픔(혈당성 식욕) 구별",
            "단백질·지방·식이섬유 비중 조정",
            "간식 빈도와 종류 재설계",
            "수분/수면이 식욕에 미치는 영향",
            "감정적 식사 인식",
        ],
        tone_guideline="공감적이면서 실행 중심. 배고픔이라는 감각 자체를 재해석하도록 돕고, 죄책감 유발 표현은 금지",
        prohibited_topics=[
            "의지박약 비난",
            "극단적 식욕 억제제 권유",
            "지나친 칼로리 제한",
        ],
    ),
    LifecycleStage.FAT_BURN: LifecycleMeta(
        description="체지방 연소 — 식습관이 형성되고 대사 유연성이 회복된 후 체지방을 적극적으로 줄이는 단계",
        focus_areas=[
            "대사 유연성과 지방산화",
            "식사 타이밍 (TRE/IF 적용 가능성)",
            "근력 운동과 단백질 충분 섭취",
            "체성분 변화 추적 (체중보다 체지방률/근육량)",
            "정체기 대응 전략",
        ],
        tone_guideline="구체적이고 실행 중심. 수치와 근거를 명확히 제시하고, 사용자의 누적된 학습을 신뢰하는 톤. 초보자용 기초 설명은 생략",
        prohibited_topics=[
            "기초 혈당 개념 재설명 (이미 학습 완료)",
            "근육 손실을 야기할 정도의 극단적 칼로리 컷",
            "건강 무시한 단기 감량 트릭",
        ],
    ),
    LifecycleStage.MAINTENANCE: LifecycleMeta(
        description="감량 유지 — 감량 목표 도달 후 요요 없이 신체 컴포지션과 혈당 안정을 장기 유지하는 단계",
        focus_areas=[
            "유지기 칼로리 재설정",
            "주말/외식/여행 시 변동 관리",
            "장기 모니터링 지표 (HbA1c, 공복혈당, 체성분)",
            "스트레스/수면/운동의 균형",
            "재발 방지 트리거 인식",
        ],
        tone_guideline="동료 코치 톤. 사용자가 이미 충분한 지식과 경험을 가졌음을 전제로, 미세 조정과 지속 가능성에 초점",
        prohibited_topics=[
            "다시 감량기로 회귀하라는 권유 (목표 달성 후 강박 유발)",
            "기초 개념 반복 설명",
            "단기 추가 감량 압박",
        ],
    ),
}


def get_stage_metadata(stage: LifecycleStage) -> LifecycleMeta:
    """Return the metadata bundle for a given lifecycle stage."""
    return LIFECYCLE_METADATA[stage]
