"""
PromptMaster V13 — GPT-4o 직접 심사 채점 엔진
────────────────────────────────────────────────
채점 방식:
  1. 사용자 프롬프트를 GPT-4o에 실제로 실행
  2. 출력 결과를 GPT-4o 심사관이 제약 조건별로 채점
  3. JSON 형식으로 점수 + 피드백 반환
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OPENAI_API_KEY = "YOUR_API_KEY"
JUDGE_MODEL    = "gpt-4o"
EXEC_MODEL     = "gpt-4o"


# ════════════════════════════════════════════════════════
#  데이터 클래스 (app.py 호환 유지)
# ════════════════════════════════════════════════════════
class ConstraintAnchors:
    def __init__(self, id: str, name: str, positive: str, negative: str, weight: float = 1.0):
        self.id       = id
        self.name     = name
        self.positive = positive
        self.negative = negative
        self.weight   = weight


class ComplianceResult:
    def __init__(self, constraint_id, constraint_name, score, feedback="", weight=1.0):
        self.constraint_id   = constraint_id
        self.constraint_name = constraint_name
        self.score           = score
        self.feedback        = feedback
        self.weight          = weight
        # 호환용 더미 필드
        self.alpha           = 0.0
        self.min_projection  = 0.0
        self.max_projection  = 1.0
        self.expert_id       = "gpt-4o-judge"

    def to_dict(self) -> dict[str, Any]:
        return {
            "constraint_id":   self.constraint_id,
            "constraint_name": self.constraint_name,
            "alpha":           self.alpha,
            "min_projection":  self.min_projection,
            "max_projection":  self.max_projection,
            "score":           round(self.score, 2),
            "weight":          round(self.weight, 4),
            "expert_id":       self.expert_id,
        }


# ════════════════════════════════════════════════════════
#  OpenAI 클라이언트
# ════════════════════════════════════════════════════════
def _get_client():
    from openai import OpenAI
    return OpenAI(api_key=OPENAI_API_KEY)


def _chat(messages: list[dict], model: str = EXEC_MODEL, temperature: float = 0.3) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=1500,
    )
    return resp.choices[0].message.content.strip()


# ════════════════════════════════════════════════════════
#  Step 1: 사용자 프롬프트를 GPT-4o에 실행
# ════════════════════════════════════════════════════════
def _execute_prompt(user_prompt: str) -> str:
    """
    사용자가 작성한 프롬프트를 GPT-4o에 실제로 실행하고 출력을 반환.
    이 출력이 채점 대상이 됨.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "당신은 사용자의 지시를 그대로 수행하는 AI 어시스턴트입니다. "
                "사용자의 지시문을 읽고 그 지시에 따라 답변을 생성하세요."
            )
        },
        {
            "role": "user",
            "content": user_prompt
        }
    ]
    return _chat(messages, model=EXEC_MODEL, temperature=0.5)


# ════════════════════════════════════════════════════════
#  Step 2: GPT-4o 심사관이 출력 결과를 채점
# ════════════════════════════════════════════════════════
def _judge_output(
    user_prompt:    str,
    llm_output:     str,
    constraints:    list[ConstraintAnchors],
) -> list[ComplianceResult]:
    """
    GPT-4o 심사관이 LLM 출력 결과를 제약 조건별로 채점.
    실제 출력을 보고 채점하므로 정확도가 높음.
    """
    constraint_list = "\n".join(
        f'{i+1}. [{c.id}] {c.name}: "{c.positive}"'
        for i, c in enumerate(constraints)
    )

    judge_prompt = f"""당신은 프롬프트 엔지니어링 채점 전문가입니다.

아래는 사용자가 AI에게 보낸 지시문(프롬프트)과, 그 지시문을 받은 AI가 생성한 실제 출력입니다.

[사용자 프롬프트]
{user_prompt}

[AI 실제 출력]
{llm_output}

[채점할 제약 조건]
{constraint_list}

위 제약 조건들을 기준으로, 사용자의 프롬프트가 AI 출력을 얼마나 잘 유도했는지 채점하세요.

채점 기준:
- 프롬프트가 해당 제약을 명확히 지시했고, 실제 AI 출력도 그것을 잘 따랐으면 높은 점수
- 프롬프트에 지시가 있었지만 출력이 따르지 않았으면 중간 점수
- 프롬프트에 지시 자체가 없었으면 낮은 점수

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트나 마크다운 없이:
{{
  "results": [
    {{
      "constraint_id": "제약ID",
      "score": 0~100 사이 숫자,
      "reason": "한국어로 2문장 이내 채점 근거"
    }}
  ]
}}"""

    resp = _chat(
        [{"role": "user", "content": judge_prompt}],
        model=JUDGE_MODEL,
        temperature=0.0,
    )

    # JSON 파싱
    clean = resp.replace("```json", "").replace("```", "").strip()
    data  = json.loads(clean)

    constraint_map = {c.id: c for c in constraints}
    results = []
    for item in data["results"]:
        cid = item["constraint_id"]
        c   = constraint_map.get(cid)
        if not c:
            continue
        results.append(ComplianceResult(
            constraint_id=cid,
            constraint_name=c.name,
            score=float(item["score"]),
            feedback=item.get("reason", ""),
            weight=c.weight,
        ))
    return results


# ════════════════════════════════════════════════════════
#  메인 엔진 (app.py 인터페이스 완전 호환)
# ════════════════════════════════════════════════════════
class PromptMasterV11:
    """
    V13 엔진 — GPT-4o 직접 실행 + GPT-4o 심사 채점.
    기존 app.py의 from_json_config / diagnose 인터페이스 유지.
    """

    def __init__(self, **kwargs) -> None:
        self._constraints: list[ConstraintAnchors] = []
        self._fitted = False

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, constraints: list[ConstraintAnchors]) -> "PromptMasterV11":
        self._constraints = constraints
        self._fitted = True
        return self

    def score_prompt(self, user_prompt: str) -> tuple[str, list[ComplianceResult]]:
        """프롬프트 실행 후 채점. (llm_output, results) 반환."""
        llm_output = _execute_prompt(user_prompt)
        results    = _judge_output(user_prompt, llm_output, self._constraints)
        return llm_output, results

    def diagnose(
        self,
        user_prompt:    str,
        constraint_ids: list[str] | None = None,
    ) -> dict[str, Any]:

        llm_output, results = self.score_prompt(user_prompt)

        if constraint_ids:
            allowed = set(constraint_ids)
            results = [r for r in results if r.constraint_id in allowed]
        if not results:
            raise ValueError("매칭되는 제약 조건이 없습니다.")

        # 가중 평균 점수
        total_w = sum(r.weight for r in results)
        overall = sum(r.score * r.weight for r in results) / (total_w or 1.0)

        return {
            "user_prompt":     user_prompt,
            "llm_output":      llm_output,       # 실제 AI 출력 (UI 표시용)
            "constraints":     [r.to_dict() for r in results],
            "overall_score":   round(overall, 2),
            "model":           JUDGE_MODEL,
            "tau_ratio":       0.0,
            "singular_values": [],
            "judge_feedback":  {r.constraint_id: r.feedback for r in results},
        }

    @classmethod
    def from_json_config(
        cls,
        config_path,
        **kwargs,
    ) -> "PromptMasterV11":
        path    = Path(config_path)
        payload = json.loads(path.read_text(encoding="utf-8"))

        constraints = [
            ConstraintAnchors(
                id=item["id"],
                name=item["name"],
                positive=item["positive"],
                negative=item["negative"],
                weight=float(item.get("weight", 1.0)),
            )
            for item in payload["constraints"]
        ]

        engine = cls()
        engine.fit(constraints)
        return engine
