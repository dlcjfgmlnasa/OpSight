# 07. LLM Placeholder + 진짜 LLM 통합

> 현재 LLM 은 *template*. 진짜 vLLM Llama 가 합류해도 interface 동일이라 내부만 교체.

## 현재 — `opsight/llm/placeholder.py`

⚠️ Placeholder: 진짜 LLM 호출 없음. tool 결과로부터 hard-coded template 채워서 텍스트 생성.

```python
def render_shallow_narration(results: list[ToolResponse]) -> str:
    """Light LLM placeholder — vLLM Llama-3.1-8B 합류 시 교체."""
    hypo = _find_first_risk(results, "predict_hypotension")
    arrest = _find_first_risk(results, "predict_cardiac_arrest")
    max_risk = max([r for r in (hypo, arrest) if r is not None], default=0.0)
    tone = _tone_for_risk(max_risk)
    base = f"[{tone}] 저혈압 risk {hypo:.2f}, 심정지 risk {arrest:.2f}."
    if tone == "위험":
        return f"{base} Deep mode 권고. [CLINICIAN-REVIEW]"
    return base
```

진짜 LLM 이 아니지만 *interface 동일*. 내부만 vLLM 호출로 교체.

## Tone 분류

```python
_TONE_BANDS: list[tuple[float, str]] = [
    (0.3, "안정"),
    (0.5, "주의"),
    (0.7, "경고"),
    (1.01, "위험"),
]

def _tone_for_risk(risk: float) -> str:
    for upper, label in _TONE_BANDS:
        if risk < upper:
            return label
    return "위험"
```

Project brief §8.1 그대로. [[20_아키텍처/9_Section_Brief]] 참조.

## `render_deep_brief` — 9-section template

```python
def render_deep_brief(results, *, surgery_type, surgery_phase, elapsed_min) -> dict[str, str]:
    sections = {
        "Surgery context":  f"수술 유형: {surgery_type}. Phase: {surgery_phase}. 경과 시간: {elapsed_min:.1f}분.",
        "Signal status":    "Modality 가용성 + 품질: " + ", ".join(f"{m}={q:.2f}" for m, q in qualities.items()),
        "Assessment confidence": f"{confidence}.",
        "Risk evaluation":  ...
        "Evidence":         "...",
        "Intraoperative context": "...",
        "Similar trajectory": "...",
        "Recommendations":  "임상적 고려사항은 임상의 판단 영역이다. [CLINICIAN-REVIEW: ...]",
        "Limitations":      "본 브리프는 placeholder template LLM 출력이다. ...",
    }
    return sections
```

9 section 모두 *항상* 채워짐 — 빈 section 없음 (LLM 누락 사고 방지).

## 진짜 LLM 통합 작업

### System prompt (이미 작성됨)

```
prompts/
├── v1_light_shallow.md            ← Light system prompt
├── v1_heavy_deep_brief.md         ← Heavy system prompt
├── v1_clinical_fact_guard.md      ← 공유 hallucination guard
├── v1_tool_description_style.md   ← tool description tone guide
├── v2_heavy_deep_brief.md         ← 21-tool source mapping + Tool 21 paraphrase 금지
└── v1_*.en.md                     ← English variants
```

각 prompt 는 vLLM 의 system message 로 전달.

**Light prompt v1**
- Role: 수술 중 환자 모니터링 보조 — 1문장 한글 narration
- Constraint: ≤ 50 tokens, 한 문장
- Tone: 상태별 (안정 / 주의 / 경고 / 위험)
- Guard: conditional phrasing + `[CLINICIAN-REVIEW]`

**Heavy prompt v1 / v2**
- Role: 9-section 한글 brief (500–800 tokens)
- Constraint: 9 section 모두 채우기, section name 영문 유지
- Tone: clinical narrative + technical rigor
- Guard: 모든 정량 claim 은 tool 결과로 grounded, dose 권고 금지
- v2 추가: 21-tool source mapping + Tool 21 paraphrase 금지

### vLLM client 통합 (다음 단계)

```python
# opsight/llm/light.py (예상)

class LightLLMClient:
    def __init__(self, model_id: str, host: str, port: int, ...):
        self._client = openai.OpenAI(base_url=f"http://{host}:{port}/v1", ...)
        self._system_prompt = _load_prompt("v1_light_shallow.md")

    def narrate(self, tool_results: list[ToolResponse]) -> str:
        user_content = self._render_tool_results(tool_results)
        resp = self._client.chat.completions.create(
            model=self._model_id,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=80,
            temperature=0.1,
        )
        return resp.choices[0].message.content
```

Placeholder 의 `render_shallow_narration` 을 위 `narrate` 로 교체. shallow_loop 코드 변경 0.

### `LLMClient` Protocol

```python
class LLMClient(Protocol):
    def narrate(self, tool_results: list[ToolResponse]) -> str: ...
    def brief(self, tool_results: list[ToolResponse], **kwargs) -> dict[str, str]: ...
```

Mock FM swap 과 같은 패턴. [[10_기초/Python_Protocol_과_runtime_checkable]].

## Clinical Fact Guard 정책

모든 LLM (placeholder, Light, Heavy) 에 적용:

❌ 잘못된 phrasing
```
"환자는 sepsis 다."
"Norepinephrine 0.05 mcg/kg/min 시작."
```

✅ 올바른 phrasing
```
"수치는 X 이며 임상의 판단 필요."
"[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]"
```

`v1_clinical_fact_guard.md` 가 system prompt 안에 명시적으로 박힘. brief §13.1.

## 시기와 분담

- **Prompt 작성** ✅ 완료 (`prompts/v1_*.md`, `v2_heavy_deep_brief.md` 8개)
- **vLLM client 코드** — 다음 단계
- **Real backend 연결** — Stage 2 GPU infrastructure 준비 후

## 다음 노트

- [[20_아키텍처/9_Section_Brief]] — 9 section 정확한 의미
- [[06_nodes_graph]] — placeholder 가 어디서 호출되는가
- [[../40_플랜/진행상황]] — 진짜 LLM 통합 현재 상태
