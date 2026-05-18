# 9-Section Brief — Deep mode 출력 형식

> Deep mode 발화 시 LLM 이 작성하는 9-section 한글 brief. 매번 같은 구조 → 임상의가 빠르게 읽음.

## 왜 자유 형식이 아니라 9 section 고정

1. **임상의 readability** — 매번 같은 구조 = 어디 봐야 할지 즉각 앎
2. **평가 가능** — Stage 4 임상의 rubric 을 section 단위로 적용
3. **환각 억제** — 정해진 슬롯 = LLM 이 채워 넣을 공간 제한
4. **Faithfulness 검증** — section 별 claim 을 tool 결과에 자동 매핑

→ 항상 **같은 9 section, 같은 순서, 한글, 500–800 tokens**.

## 9 sections

| # | Section (영문 ID) | 한글 의미 | 내용 |
|---|------------------|----------|------|
| 1 | `[Surgery context]` | 수술 맥락 | surgery type, phase, 경과 시간 |
| 2 | `[Signal status]` | 신호 상태 | modality 가용성 + 품질 + cross-modal consistency |
| 3 | `[Assessment confidence]` | 평가 신뢰도 | `HIGH / MEDIUM / LOW / UNRELIABLE` |
| 4 | `[Risk evaluation]` | 위험 평가 | 주요 risk score, horizon |
| 5 | `[Evidence]` | 근거 | modality 별 trend + cross-modal 검증 |
| 6 | `[Intraoperative context]` | 수술 중 맥락 | 마취제 / 혈관활성제 / 수액 / phase |
| 7 | `[Similar trajectory]` | 유사 case | N개 similar case (가용 시) |
| 8 | `[Recommendations]` | 권고 | *고려사항 만*, dose 권고 X, `[CLINICIAN-REVIEW]` 필수 |
| 9 | `[Limitations]` | 한계 | 신호 품질 / 누락 modality / caveat |

**Section 이름은 영문 유지** — 시스템 식별자 (LLM 이 한글로 의역하면 parser 깨짐). 본문은 한글.

## Shallow narration — 1 문장 한글

Brief 와 달리 **1문장 ≤ 50 tokens**. 상태별 톤:

| 상태 | 조건 (max risk) | 톤 |
|------|----------------|-----|
| 안정 | < 0.3 | 짧고 담백 |
| 주의 | 0.3 – 0.5 | 추세 명시 |
| 경고 | 0.5 – 0.7 | 명확한 우려 |
| 위험 | > 0.7 | "Deep mode 권고" 포함, `[CLINICIAN-REVIEW]` |

예시:
- 안정: `"[안정] 저혈압 risk 0.15, 심정지 risk 0.03."`
- 주의: `"[주의] 저혈압 risk 0.42, 추세 모니터링 필요."`
- 경고: `"[경고] 저혈압 risk 0.65, 추세 모니터링 필요."`
- 위험: `"[위험] 저혈압 risk 0.85. Deep mode 권고. [CLINICIAN-REVIEW]"`

## 현재 placeholder LLM 의 9-section 예시

`opsight/llm/placeholder.py::render_deep_brief()` 출력:

```
[Surgery context]   수술 유형: general. Phase: maintenance. 경과 시간: 90.0분.
[Signal status]      Modality 가용성 + 품질: ABP=0.95.
[Assessment confidence]   HIGH.
[Risk evaluation]    저혈압 risk: 0.85 (5분 horizon). 심정지 risk: 0.04 (5분 horizon).
[Evidence]           Modality 별 추세 및 cross-modal 검증은 후속 작업에서 LLM 이 채움 (placeholder).
[Intraoperative context]  마취제 / 혈관활성제 / 수액 정보는 EMR tool 결과에서 합성 (stub 사용).
[Similar trajectory]  Similar case 검색은 tool 13 미구현 — TBD.
[Recommendations]    임상적 고려사항은 임상의 판단 영역. [CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]
[Limitations]        본 브리프는 placeholder template LLM 출력. 진단/처방 권고가 아님. [CLINICIAN-REVIEW]
```

Template 기반. 진짜 LLM (vLLM Llama-3.3-70B) 교체 시 같은 자리에 자연어. [[30_코드_워크스루/07_llm_placeholder_와_plan_1_6]] 참조.

## 진짜 LLM 통합 흐름

1. **System prompt** (`prompts/v1_heavy_deep_brief.md`)
   - 9-section 구조 + 한글 + 500–800 tokens
   - `[Recommendations]` dose 권고 금지
   - 임상 단정은 `[CLINICIAN-REVIEW]`
2. **User context** — 21 tool 결과를 JSON 으로 첨부 (Signal Access 17–21 포함)
3. **LLM 호출** → 9-section text 반환
4. **Parser** — section 헤더 기준 분리 → `BriefRecord.sections` dict

Heavy LLM prompt v2 (`prompts/v2_heavy_deep_brief.md`) 에 21-tool source mapping + Tool 21 paraphrase 금지 enforce.

## "Recommendations dose 권고 금지" 정책

Brief §13.1 Clinical Fact Guard.

❌
```
[Recommendations]  Norepinephrine 0.05 mcg/kg/min 시작 권고.
```

✅
```
[Recommendations]  저혈압 위험도 상승 추세이며, 임상의의 vasopressor 사용
                   여부 판단이 필요할 수 있다. [CLINICIAN-REVIEW]
```

차이:
- 구체 dose / 약물 명시 ❌
- Conditional phrasing + `[CLINICIAN-REVIEW]` ✅
- 결정 권한이 임상의에게

## Faithfulness — 모든 정량 claim 은 tool 결과 grounded

```
"저혈압 risk: 0.85 (5분 horizon)"
            ▲              ▲
            │              └── tool 1 args.horizon_min
            └── tool 1 result.risk
```

LLM 이 "0.92" 라 환각하면 faithfulness 0. trace 자동 검증.

Stage 3 에서 *atomic-claim grounding* 자동화 (brief §11.1).

## 21 tool 의 9-section source mapping

| Brief section | 주 source | 보조 |
|---------------|-----------|------|
| `[Surgery context]` | 11 + **21** | 15 |
| `[Signal status]` | **17** + **18** + 3 | 4 |
| `[Assessment confidence]` | 3 + 4 | — |
| `[Risk evaluation]` | 1 + 2 | — |
| `[Evidence]` | 5 + 6 + 7 + **19** + **20** | — |
| `[Intraoperative context]` | 8 + 9 + 10 | 11 |
| `[Similar trajectory]` | 13 | — |
| `[Recommendations]` | (LLM 합성) | 14 |
| `[Limitations]` | (LLM 합성) | 모든 tool 의 `quality_meta` |

자세한 21 tool: [[21_Tool_Suite]].

## 다음 노트

- [[Dual_mode_architecture]] — Shallow vs Deep
- [[21_Tool_Suite]] — Brief 에 들어가는 tool 결과
- [[30_코드_워크스루/07_llm_placeholder_와_plan_1_6]] — placeholder → 진짜 LLM
