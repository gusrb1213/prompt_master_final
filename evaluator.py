"""
evaluator.py — GPT-4o 심사 결과 → 최종 평가 변환
"""
from __future__ import annotations
from typing import Any

COACH_TIPS = [
    "과제 상황(누가, 무엇을, 왜)을 한 문장으로 요약한 뒤 출력 형식을 고정하세요.",
    "제약은 '반드시', '만', '이하'처럼 검증 가능한 표현으로 쓰세요.",
    "모델에게 할 일(분석·요약·번역)과 출력 규칙(형식·톤·분량)을 분리해 적으면 점수가 올라갑니다.",
]


def _grade(overall: float, pass_threshold: float) -> str:
    if overall >= pass_threshold + 15:
        return "A"
    if overall >= pass_threshold:
        return "B"
    if overall >= pass_threshold - 15:
        return "C"
    return "D"


def build_evaluation(
    diagnosis: dict[str, Any],
    scenario_title: str,
    pass_threshold: float = 60.0,
) -> dict[str, Any]:
    overall  = float(diagnosis["overall_score"])
    passed   = overall >= pass_threshold
    grade    = _grade(overall, pass_threshold)

    # GPT-4o 심사관이 생성한 제약별 피드백 활용
    judge_feedback = diagnosis.get("judge_feedback", {})

    items: list[dict[str, Any]] = []
    for row in diagnosis["constraints"]:
        cid      = row["constraint_id"]
        score    = float(row["score"])
        feedback = judge_feedback.get(cid, "채점 피드백을 불러오는 중 오류가 발생했습니다.")
        item_pass = score >= max(pass_threshold - 15, 40)
        items.append({**row, "passed": item_pass, "feedback": feedback})

    weak = sorted(items, key=lambda x: x["score"])[:1]
    summary = (
        f"시나리오 「{scenario_title}」 기준 종합 {overall:.1f}점 ({grade}등급). "
        + ("제출하신 프롬프트가 과제 요구를 충족합니다." if passed
           else "일부 제약 축에서 지시가 부족합니다. 아래 피드백을 반영해 수정해 보세요.")
    )
    if not passed and weak:
        summary += f" 우선 개선: {weak[0]['constraint_name']} ({weak[0]['score']:.1f}점)."

    result = {
        "overall_score": overall,
        "grade":         grade,
        "passed":        passed,
        "pass_threshold": pass_threshold,
        "summary":       summary,
        "constraints":   items,
        "coach_tips":    COACH_TIPS,
    }

    # AI 실제 출력이 있으면 포함 (UI에서 보여줄 수 있음)
    if "llm_output" in diagnosis:
        result["llm_output"] = diagnosis["llm_output"]

    return result
