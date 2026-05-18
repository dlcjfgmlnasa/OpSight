# 9-Section Brief — Deep mode 의 출력 형식

> Deep mode 가 발화하면 LLM 이 작성하는 정해진 9개 섹션짜리 한글 문서. 매번 같은 구조라서 임상의가 빠르게 읽을 수 있다.

## 왜 자유 형식이 아니라 9 섹션 고정인가

LLM 에게 "지금 상황을 정리해줘" 라고 하면 매번 다른 구조로 나온다. 어떤 case 는 risk 부터, 어떤 case 는 신호 품질부터, 어떤 case 는 약물 정보부터. 이건 네 가지 면에서 불리하다.

1. **임상의가 빠르게 읽기 힘들다.** 매번 어디를 봐야 할지 다시 찾아야 한다. 매 30초 ~ 5분마다 새 brief 가 나오는 상황에선 치명적이다.
2. **평가가 어렵다.** 임상의 평가 rubric (Stage 4) 을 섹션 단위로 적용할 수 없다.
3. **환각 가능성이 늘어난다.** 자유 형식일수록 LLM 이 마음대로 채워 넣을 공간이 커진다. 정해진 슬롯이 있으면 그 자리에 무엇이 와야 하는지가 명확해진다.
4. **Faithfulness 검증이 어렵다.** 각 섹션의 정량 claim 이 어느 tool 결과에서 왔는지를 자동으로 매핑하려면, 섹션이 고정되어 있어야 한다.

그래서 brief 는 항상 **같은 9 섹션, 같은 순서, 한글, 500–800 token**.

## 9 섹션이 무엇을 담는가

| # | 섹션 이름 (영문 식별자) | 한글 의미 | 무엇이 들어가나 |
|---|------------------------|----------|----------------|
| 1 | `[Surgery context]` | 수술 맥락 | 수술 유형, 현재 phase, 경과 시간 |
| 2 | `[Signal status]` | 신호 상태 | 어떤 modality 가 가용한가, 품질은 어떤가, cross-modal 일치도 |
| 3 | `[Assessment confidence]` | 평가 신뢰도 | HIGH / MEDIUM / LOW / UNRELIABLE 중 하나 |
| 4 | `[Risk evaluation]` | 위험 평가 | 주요 risk score, horizon (몇 분 앞을 예측한 건지) |
| 5 | `[Evidence]` | 근거 | modality 별 추세, cross-modal 검증 |
| 6 | `[Intraoperative context]` | 수술 중 맥락 | 마취제, 혈관활성제, 수액, 진행 단계 |
| 7 | `[Similar trajectory]` | 유사 case | 가용 시 N개의 유사 case (현재는 stub) |
| 8 | `[Recommendations]` | 권고 | *고려사항만*, dose 권고 금지, `[CLINICIAN-REVIEW]` 필수 |
| 9 | `[Limitations]` | 한계 | 신호 품질 문제, 누락 modality, 그 외 caveat |

**섹션 이름은 영문을 그대로 유지** 한다 — 시스템 식별자이기 때문에. LLM 이 한글로 의역하면 parser 가 망가진다. 본문 내용은 한글.

## Shallow 의 한 줄 narration 은 어떻게 다른가

Deep brief 가 9 섹션이라면 Shallow 는 **한 줄, 50 token 이하**. 상태별 톤이 정해져 있다.

| 상태 | 조건 (최대 risk) | 톤 |
|------|----------------|-----|
| 안정 | < 0.3 | 짧고 담백 |
| 주의 | 0.3 – 0.5 | 추세를 언급 |
| 경고 | 0.5 – 0.7 | 명확한 우려 표현 |
| 위험 | > 0.7 | "Deep mode 권고" 포함, `[CLINICIAN-REVIEW]` |

실제 예시:

- 안정: `"[안정] 저혈압 risk 0.15, 심정지 risk 0.03."`
- 주의: `"[주의] 저혈압 risk 0.42, 추세 모니터링 필요."`
- 경고: `"[경고] 저혈압 risk 0.65, 추세 모니터링 필요."`
- 위험: `"[위험] 저혈압 risk 0.85. Deep mode 권고. [CLINICIAN-REVIEW]"`

## 현재 placeholder LLM 이 만드는 9 섹션 예시

진짜 LLM 이 합류하기 전까지는 `vitalagent/llm/placeholder.py::render_deep_brief()` 가 template 기반으로 9 섹션을 채운다. 모양은 이렇다.

```
[Surgery context]   수술 유형: general. Phase: maintenance. 경과 시간: 90.0분.
[Signal status]      Modality 가용성 + 품질: ABP=0.95.
[Assessment confidence]   HIGH.
[Risk evaluation]    저혈압 risk: 0.85 (5분 horizon). 심정지 risk: 0.04 (5분 horizon).
[Evidence]           Modality 별 추세 및 cross-modal 검증은 후속 작업에서 LLM 이 채운다 (placeholder).
[Intraoperative context]  마취제 / 혈관활성제 / 수액 정보는 EMR tool 결과에서 합성된다 (stub 사용 중).
[Similar trajectory]  Similar case 검색은 tool 13 (find_similar_cases) 미구현 — TBD.
[Recommendations]    임상적 고려사항은 임상의 판단 영역이다. [CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]
[Limitations]        본 브리프는 placeholder template LLM 출력이다. 진단 / 처방 권고가 아니며, mock FM 데이터가 포함될 수 있다. [CLINICIAN-REVIEW]
```

지금은 빈 자리에 "후속 작업에서 채워질 예정" 같은 문구가 들어가 있다. 진짜 LLM (vLLM Llama-3.3-70B) 이 합류하면 같은 자리에 실제 자연어가 생성된다. 코드 워크스루는 [[30_코드_워크스루/07_llm_placeholder_와_plan_1_6]].

## 진짜 LLM 이 brief 를 어떻게 만들 것인가

진짜 LLM 이 합류했을 때 흐름은 다음과 같다.

1. **System prompt** (`prompts/v1_heavy_deep_brief.md`) 에서 다음을 명시
    - 9 섹션 구조, 한글, 500–800 token 한도
    - `[Recommendations]` 는 dose 권고 금지
    - 임상 단정은 반드시 `[CLINICIAN-REVIEW]` marker
2. **User context** 에 21개 tool 의 결과를 JSON 으로 첨부 (Signal Access 17–21 포함)
3. **LLM 호출** → 9 섹션 텍스트 반환
4. **Parser** 가 섹션 헤더를 기준으로 잘라서 `BriefRecord.sections` dict 에 저장

Heavy LLM prompt v2 (`prompts/v2_heavy_deep_brief.md`) 에는 21 tool source mapping 과 Tool 21 의 paraphrase 금지가 enforce 되어 있다.

## "Recommendations 섹션은 dose 권고 금지" — 가장 중요한 정책

Project brief §13.1 (Clinical Fact Guard) 에 따라 이 섹션은 특히 조심해야 한다.

❌ 잘못된 phrasing
```
[Recommendations]  Norepinephrine 0.05 mcg/kg/min 시작 권고.
```

✅ 올바른 phrasing
```
[Recommendations]  저혈압 위험도가 상승하는 추세이며, 임상의의 vasopressor 사용
                   여부 판단이 필요할 수 있다. [CLINICIAN-REVIEW]
```

차이는 세 가지다.

- 구체적인 약물 이름 / dose 명시 ❌
- conditional phrasing + `[CLINICIAN-REVIEW]` marker ✅
- 결정 권한이 임상의에게 있음을 명시

## Faithfulness — 모든 정량 claim 은 tool 결과에서 와야 한다

Brief 안의 *숫자* 는 모두 tool 결과에서 와야 한다. LLM 이 만들어낸 숫자면 환각이다.

```
"저혈압 risk: 0.85 (5분 horizon)"
            ▲              ▲
            │              └── tool 1 의 args.horizon_min
            └── tool 1 의 result.risk
```

만약 LLM 이 "0.92" 라고 환각하면 faithfulness 점수 0. trace 에 들어 있는 tool 결과와 brief 의 숫자를 자동 매칭해서 검증한다. 이걸 *atomic-claim grounding* 이라고 부르고, 자동화는 Stage 3 (full agent) 에서 작성 예정 (project brief §11.1).

## 21개 tool 결과가 9 섹션에 어떻게 매핑되나

각 섹션의 정량 source 는 정해진 tool 들이다. Heavy LLM prompt v2 의 worked-through 예시도 이 매핑을 따른다.

| Brief 섹션 | 주 source tool | 보조 |
|---|---|---|
| `[Surgery context]` | 11 `query_surgery_progress` + 21 `summarize_current_state` | 15 `surgery_context_awareness` |
| `[Signal status]` | 17 `get_current_vitals` + 18 `describe_signal` + 3 `assess_signal_quality` | 4 `cross_modal_consistency` |
| `[Assessment confidence]` | 3 + 4 | — |
| `[Risk evaluation]` | 1 `predict_hypotension` + 2 `predict_cardiac_arrest` | — |
| `[Evidence]` | 5 + 6 + 7 + 19 `assess_variability` + 20 `compare_to_baseline` | — |
| `[Intraoperative context]` | 8 + 9 + 10 | 11 |
| `[Similar trajectory]` | 13 `find_similar_cases` | — |
| `[Recommendations]` | (LLM 합성) | 14 `intervention_response_prediction` |
| `[Limitations]` | (LLM 합성) | 모든 tool 의 `quality_meta` |

자세한 21개 tool 의 spec 은 [[21_Tool_Suite]].

## 다음 노트

- [[Dual_mode_architecture]] — Shallow narration vs Deep brief 가 어떻게 한 graph 안에 공존하는가
- [[21_Tool_Suite]] — Brief 에 들어가는 tool 결과 21개의 전체 카탈로그
- [[30_코드_워크스루/07_llm_placeholder_와_plan_1_6]] — placeholder 에서 진짜 LLM 으로 교체하는 작업
