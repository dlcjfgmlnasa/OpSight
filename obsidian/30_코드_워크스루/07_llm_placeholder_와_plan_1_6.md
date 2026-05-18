# 07. LLM Placeholder — 진짜 LLM 자리에 임시 template 이 들어가 있다

> 지금 LLM 자리에는 **하드코딩된 template** 이 있다. 진짜 vLLM Llama 가 들어올 때 *interface 만 동일* 하게 유지하면서 내부를 교체한다. 그 위치에 들어갈 system prompt 7개는 이미 작성되어 있다.

## 현재 상태 — `vitalagent/llm/placeholder.py`

⚠️ Placeholder 다. 진짜 LLM 호출이 없다. tool 결과를 받아서 하드코딩된 template 의 자리를 채워 텍스트를 만든다.

```python
def render_shallow_narration(results: list[ToolResponse]) -> str:
    """Light LLM placeholder — 진짜 vLLM Llama-3.1-8B 가 합류할 때 교체된다."""
    hypo = _find_first_risk(results, "predict_hypotension")
    arrest = _find_first_risk(results, "predict_cardiac_arrest")
    max_risk = max([r for r in (hypo, arrest) if r is not None], default=0.0)
    tone = _tone_for_risk(max_risk)
    base = f"[{tone}] 저혈압 risk {hypo:.2f}, 심정지 risk {arrest:.2f}."
    if tone == "위험":
        return f"{base} Deep mode 권고. [CLINICIAN-REVIEW]"
    return base
```

진짜 LLM 이 아니지만 **interface 는 동일** 하다 — `list[ToolResponse]` 를 받아서 `str` 을 반환. shallow_loop 코드는 이 함수의 내부가 LLM 호출로 바뀌어도 알지 못한다.

## Tone 분류 — risk 값에 따른 한글 라벨

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

Project brief §8.1 의 4단계 톤을 그대로 옮긴 것. 자세한 의미는 [[20_아키텍처/9_Section_Brief]].

## `render_deep_brief` — 9개 섹션의 template

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

핵심 invariant: **9 섹션이 모두 *항상* 채워진다.** 빈 섹션이 없다. LLM 이 섹션 하나를 누락하는 사고를 placeholder 단계에서 미리 차단한다.

## 진짜 LLM 합류 시 무엇이 바뀌나

System prompt 작업과 vLLM 통합 작업으로 나뉜다.

### System prompt 들 — 이미 작성됨

```
prompts/
├── v1_light_shallow.md            ← Light LLM 의 shallow narration 용
├── v1_heavy_deep_brief.md         ← Heavy LLM 의 deep brief 용
├── v1_clinical_fact_guard.md      ← 두 prompt 가 공유하는 hallucination guard
├── v1_tool_description_style.md   ← tool description 의 톤 가이드
├── v2_heavy_deep_brief.md         ← 21-tool source mapping + Tool 21 paraphrase 금지 강제
└── v1_*.en.md                     ← 영문 변형
```

각 prompt 는 vLLM 에게 system message 로 전달된다. 작성된 내용 요약:

**Light prompt v1**
- 역할: 수술 중 환자 모니터링 보조 — 한 문장 한글 narration
- 제약: 50 token 이하, 한 문장
- 톤: 상태별 4단계 (안정 / 주의 / 경고 / 위험)
- Hallucination guard: 모든 임상 단정은 conditional phrasing + `[CLINICIAN-REVIEW]`

**Heavy prompt v1 / v2**
- 역할: 9 섹션 한글 brief 생성 (500–800 token)
- 제약: 9 섹션 모두 채우기, 섹션 이름은 영문 그대로 유지
- 톤: clinical narrative + technical rigor 의 균형
- Hallucination guard: 모든 정량 claim 은 tool 결과로 grounded, dose 권고 금지
- v2 추가: 21 tool 의 source mapping worked-through 예시 + Tool 21 paraphrase 금지 enforce

### vLLM client 통합 — 다음 단계 작업

```python
# vitalagent/llm/light.py (예상 모양)

class LightLLMClient:
    def __init__(self, model_id: str, host: str, port: int, ...):
        # vLLM 의 OpenAI 호환 server 에 연결
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

placeholder 의 `render_shallow_narration` 을 위 `narrate` 로 치환. shallow_loop 코드는 변경 없음.

### `LLMClient` Protocol — 모든 LLM 이 같은 interface 를 만족

```python
class LLMClient(Protocol):
    def narrate(self, tool_results: list[ToolResponse]) -> str: ...
    def brief(self, tool_results: list[ToolResponse], **kwargs) -> dict[str, str]: ...
```

Mock FM 이 Protocol 로 swap 되는 것과 같은 패턴이 LLM 에도 적용된다. placeholder / Light / Heavy 가 모두 이 Protocol 을 만족하면 자유롭게 교체 가능. 자세한 mechanism 은 [[10_기초/Python_Protocol_과_runtime_checkable]].

## 모든 LLM 출력에 적용되는 정책 — Clinical Fact Guard

placeholder 든 Light 든 Heavy 든, 다음은 공통이다.

❌ 잘못된 phrasing
```
"환자는 sepsis 다."
"Norepinephrine 0.05 mcg/kg/min 시작."
```

✅ 올바른 phrasing
```
"수치는 X 이며 임상의 판단이 필요할 수 있다."
"[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]"
```

`v1_clinical_fact_guard.md` 가 시스템 prompt 안에 *명시적으로* 박혀서, LLM 이 매번 이 정책을 따르도록 강제한다. 자세한 정책은 project brief §13.1.

## 시기와 분담

- **Prompt 작성** — 이미 완료. `prompts/v1_*.md`, `v2_heavy_deep_brief.md` 포함 8개 파일.
- **vLLM client 코드** — 다음 단계. placeholder 를 `LightLLMClient` / `HeavyLLMClient` 로 교체.
- **Real backend 연결** — Stage 2 의 GPU infrastructure 준비 후.

## 다음 노트

- [[20_아키텍처/9_Section_Brief]] — 9 섹션 brief 의 정확한 의미
- [[06_nodes_graph]] — placeholder 가 어디서 호출되는가
- [[../40_플랜/진행상황]] — 진짜 LLM 통합의 현재 상태
