"""Placeholder template LLM (plan_1.8 task 6).
Placeholder template LLM (plan_1.8 task 6).

⚠️ This module is a **placeholder** for the real Light (Llama-3.1-8B) and
   Heavy (Llama-3.3-70B) LLMs. It does NOT call an LLM — it renders a
   template from the tool results. Replaced by vLLM-backed implementations
   when plan_1.6 (system prompts v1) lands.
⚠️ 본 module은 real Light (Llama-3.1-8B) / Heavy (Llama-3.3-70B) LLM의
   **placeholder**다. 실제 LLM을 호출하지 않으며 tool 결과로부터 template을
   렌더링한다. plan_1.6 (system prompt v1) 도착 시 vLLM 기반 구현으로 대체.

Clinical Fact Guard (project_brief §13.1): the rendered text uses cautious
phrasing and a ``[CLINICIAN-REVIEW]`` marker for any risk-level call.
임상 사실 가드 (project_brief §13.1): 렌더링되는 텍스트는 신중한 phrasing과
risk 수준 단정에 대한 ``[CLINICIAN-REVIEW]`` marker를 사용한다.
"""
from __future__ import annotations

from typing import Iterable

from opsight.tools.envelope import ToolResponse


# Tone thresholds per project_brief §8.1 / brief §8.1의 톤 임계.
_TONE_BANDS: list[tuple[float, str]] = [
    (0.3, "안정"),
    (0.5, "주의"),
    (0.7, "경고"),
    (1.01, "위험"),  # ≤ 1.0 catch-all
]


def _tone_for_risk(risk: float) -> str:
    """Map a risk value to a Korean tone label (안정 / 주의 / 경고 / 위험).
    Risk 값을 한글 톤 label에 매핑.
    """
    for upper, label in _TONE_BANDS:
        if risk < upper:
            return label
    return "위험"


def _find_first_risk(results: Iterable[ToolResponse], tool_name: str) -> float | None:
    """Return the first ``risk`` value found in results from ``tool_name``.
    ``tool_name``의 결과에서 첫 ``risk`` 값을 반환.
    """
    for r in results:
        if r.tool_name == tool_name and r.ok and r.result is not None:
            risk = r.result.get("risk")
            if isinstance(risk, (int, float)):
                return float(risk)
    return None


def render_shallow_narration(results: list[ToolResponse]) -> str:
    """Render a single-sentence Korean narration for the shallow loop.
    Shallow loop를 위한 1문장 한글 narration 렌더링.

    Light LLM placeholder — replaced by vLLM Llama-3.1-8B when plan_1.6
    delivers ``prompts/v1_light_shallow.md``.
    Light LLM placeholder — plan_1.6의 ``prompts/v1_light_shallow.md`` 도착 시
    vLLM Llama-3.1-8B로 대체.

    Output rule / 출력 규칙 (project_brief §8.1):
    - ≤ 50 tokens, single sentence.
    - tone keyword (안정 / 주의 / 경고 / 위험) reflects the maximum risk.
    - 위험 band → includes "Deep mode 권고".
    - 50 tokens 이하, 1문장.
    - 톤 키워드는 최대 risk를 반영.
    - 위험 band → "Deep mode 권고" 포함.
    """
    hypo = _find_first_risk(results, "predict_hypotension")
    arrest = _find_first_risk(results, "predict_cardiac_arrest")
    risks = [r for r in (hypo, arrest) if r is not None]
    max_risk = max(risks) if risks else 0.0
    tone = _tone_for_risk(max_risk)

    hypo_str = f"{hypo:.2f}" if hypo is not None else "—"
    arrest_str = f"{arrest:.2f}" if arrest is not None else "—"

    base = f"[{tone}] 저혈압 risk {hypo_str}, 심정지 risk {arrest_str}."
    if tone == "위험":
        return f"{base} Deep mode 권고. [CLINICIAN-REVIEW]"
    if tone in ("경고", "주의"):
        return f"{base} 추세 모니터링 필요."
    return base


_BRIEF_SECTION_ORDER: tuple[str, ...] = (
    "Surgery context",
    "Signal status",
    "Assessment confidence",
    "Risk evaluation",
    "Evidence",
    "Intraoperative context",
    "Similar trajectory",
    "Recommendations",
    "Limitations",
)


def render_deep_brief(
    results: list[ToolResponse],
    *,
    surgery_type: str = "general",
    surgery_phase: str = "maintenance",
    elapsed_min: float = 0.0,
) -> dict[str, str]:
    """Render the 9-section Korean deep brief (project_brief §8).
    9-section 한글 deep 브리프 렌더링 (project_brief §8).

    Heavy LLM placeholder — replaced by vLLM Llama-3.3-70B when plan_1.6
    delivers ``prompts/v1_heavy_deep_brief.md``.
    Heavy LLM placeholder — plan_1.6의 ``prompts/v1_heavy_deep_brief.md`` 도착
    시 vLLM Llama-3.3-70B로 대체.

    Returns:
        Dict from section name → Korean prose. All 9 sections always
        present (empty string if no data).
        section 이름 → 한글 본문 dict. 9 section 모두 항상 존재 (데이터 없을
        시 빈 문자열).
    """
    hypo = _find_first_risk(results, "predict_hypotension")
    arrest = _find_first_risk(results, "predict_cardiac_arrest")

    # Modality availability from quality results / 품질 결과로부터 modality 가용성.
    qualities: dict[str, float] = {}
    for r in results:
        if r.tool_name == "assess_signal_quality" and r.ok and r.result is not None:
            mod = r.result.get("score")
            if isinstance(mod, (int, float)) and r.args.get("modality"):
                qualities[str(r.args["modality"])] = float(mod)

    overall_quality = (
        sum(qualities.values()) / len(qualities) if qualities else None
    )
    confidence = (
        "HIGH" if (overall_quality or 0) >= 0.7
        else "MEDIUM" if (overall_quality or 0) >= 0.4
        else "LOW" if overall_quality is not None
        else "UNRELIABLE"
    )

    sections = {
        "Surgery context": (
            f"수술 유형: {surgery_type}. Phase: {surgery_phase}. "
            f"경과 시간: {elapsed_min:.1f}분."
        ),
        "Signal status": (
            "Modality 가용성 + 품질: "
            + (", ".join(f"{m}={q:.2f}" for m, q in qualities.items()) or "기록 없음")
            + "."
        ),
        "Assessment confidence": f"{confidence}.",
        "Risk evaluation": (
            f"저혈압 risk: {hypo:.2f} (5분 horizon). "
            if hypo is not None
            else "저혈압 risk: 데이터 부족. "
        )
        + (
            f"심정지 risk: {arrest:.2f} (5분 horizon)."
            if arrest is not None
            else "심정지 risk: 데이터 부족."
        ),
        "Evidence": "Modality별 trend 및 cross-modal 검증은 후속 plan_1.6에서 LLM이 채운다 (placeholder).",
        "Intraoperative context": "마취제 / 혈관활성제 / 수액 정보는 EMR tool 결과에서 합성된다 (plan_1.3 stub 사용 중).",
        "Similar trajectory": "Similar case 검색은 tool 13 (find_similar_cases) 미구현 — TBD.",
        "Recommendations": (
            "임상적 고려사항은 임상의 판단 영역이다. "
            "[CLINICIAN-REVIEW: 의료진 검토 필요]"
        ),
        "Limitations": (
            "본 브리프는 placeholder template LLM 출력이다. 진단 / 처방 권고가 "
            "아니며, mock FM Tier 1 (random) 데이터가 포함될 수 있다. "
            "[CLINICIAN-REVIEW]"
        ),
    }
    # Sanity / 정확성: 9 sections, fixed order.
    assert set(sections.keys()) == set(_BRIEF_SECTION_ORDER)
    return {name: sections[name] for name in _BRIEF_SECTION_ORDER}


__all__ = ["render_shallow_narration", "render_deep_brief"]
