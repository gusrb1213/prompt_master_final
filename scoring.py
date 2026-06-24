"""
scoring.py — 난이도별 점수 / 감점 / 힌트 반감 로직
"""
from __future__ import annotations

# ── 난이도별 점수표 ────────────────────────────────────────
LEVEL_SCORE: dict[str, int] = {
    "beginner":     10,
    "elementary":   20,
    "intermediate": 40,
    "advanced":     70,
    "expert":       100,
}

# 오답 시 감점 비율 (획득 점수의 비율)
PENALTY_RATIO = 0.5   # 틀리면 배점의 50% 감점
HINT_RATIO    = 0.5   # 힌트 사용 시 획득 점수 50%


def base_score(level: str) -> int:
    """난이도별 기본 배점 반환."""
    return LEVEL_SCORE.get(level, 10)


def calc_score(level: str, passed: bool, hint_used: bool) -> int:
    """
    실제 점수 변화량 계산 (양수=획득, 음수=감점).
    - 통과 + 힌트 없음: 전체 점수
    - 통과 + 힌트 사용: 전체 점수 × 50%
    - 실패: -(전체 점수 × 50%) 감점
    """
    pts = base_score(level)
    if passed:
        earned = pts if not hint_used else int(pts * HINT_RATIO)
        return earned
    else:
        return -int(pts * PENALTY_RATIO)


# ── 티어(랭크) 시스템 ─────────────────────────────────────
TIERS = [
    {"name": "언랭크",       "min": 0,    "color": "#9CA3AF"},
    {"name": "브론즈",       "min": 50,   "color": "#CD7F32"},
    {"name": "실버",         "min": 200,  "color": "#A8A9AD"},
    {"name": "골드",         "min": 500,  "color": "#FFD700"},
    {"name": "플래티넘",     "min": 1000, "color": "#4ECDC4"},
    {"name": "다이아몬드",   "min": 1800, "color": "#66B2FF"},
    {"name": "마스터",       "min": 2800, "color": "#C084FC"},
    {"name": "그랜드마스터", "min": 4000, "color": "#F87171"},
    {"name": "챌린저",       "min": 5500, "color": "#FBBF24"},
]


def get_tier(score: int) -> dict:
    tier = TIERS[0]
    for t in TIERS:
        if score >= t["min"]:
            tier = t
    return tier


def get_next_tier(score: int) -> dict | None:
    for t in TIERS:
        if t["min"] > score:
            return t
    return None


def tier_progress(score: int) -> float:
    """현재 티어 내 진행률 0.0~1.0."""
    cur = get_tier(score)
    nxt = get_next_tier(score)
    if nxt is None:
        return 1.0
    span = nxt["min"] - cur["min"]
    return min((score - cur["min"]) / span, 1.0)
