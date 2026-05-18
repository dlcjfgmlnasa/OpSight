# plan_1.6 — System Prompts v1 (Light + Heavy LLM)

**Owner**: `llm-prompt-engineer`
**Assist**: `biomedical-ai-paper-writer` (tone / 한글 학술 register)
**Status**: ✅ done (Sprint 4, 2026-05-17)
**Goal**: Light LLM (Llama-3.1-8B) 와 Heavy LLM (Llama-3.3-70B) 용 v1 system prompt를 작성한다. hallucination guard 와 9-section 한글 브리프 generator template을 포함한다.

> Project brief: `docs/project_brief.md §8`.

---

## Tasks

- [x] **[Priority: High]** Light LLM (8B) shallow-narration system prompt 초안.
  - 입력: brief §8.1 (1문장 ≤ 50 tokens 한글, 상태별 톤), `plan_1.5`의 surgery context
  - 출력: `prompts/v1_light_shallow.md` — 전체 system prompt + 4개 상태별 톤 예시 (안정 / 주의 / 경고 / 위험)
  - 의존성: `plan_1.5` 부분 진행
  - 참고: Light LLM은 tool 호출 X — score 입력만 받아 1문장 narration. 위험 상태 narration에는 `[CLINICIAN-REVIEW]` marker 필수.

- [x] **[Priority: High]** Heavy LLM (70B) deep-brief system prompt 초안.
  - 입력: brief §8 (9-section 한글 template, 500–800 tokens), tool-call 결과 schema (`plan_1.7` 참조 예정)
  - 출력: `prompts/v1_heavy_deep_brief.md` — 전체 system prompt + 1개 walked-through 예시 브리프 (synthetic)
  - 의존성: `plan_1.7` schema 초안
  - 참고: brief §8.6 / §8.8 (Recommendations) section은 **임상 단정 금지**. 모든 권고는 조건문 (conditional) phrasing + `[CLINICIAN-REVIEW]`.

- [x] **[Priority: High]** Hallucination-guard block 초안 (Light / Heavy 양쪽이 공유).
  - 입력: `docs/project_brief.md §13.1` Clinical Fact Guard
  - 출력: `prompts/v1_clinical_fact_guard.md` — drop-in block, 양 system prompt에 reference로 포함됨
  - 의존성: 없음
  - 참고: Light prompt에도 포함 (1문장 안에서도 단정 금지). 한·영 bilingual.

- [x] **[Priority: Medium]** `plan_1.7`을 위한 tool description tone guide.
  - 입력: 7 FM + 5 EMR + 2 Knowledge + 2 Auxiliary = 16 tool surface
  - 출력: `prompts/v1_tool_description_style.md` — 각 tool description을 *어떻게* 작성할지에 대한 guide (LLM-readable, 짧음, failure mode 포함, leakage guard 언급)
  - 의존성: 없음
  - 참고: `plan_1.7` owner인 langgraph-engineer가 본 style guide를 따라 description을 작성한다.

- [x] **[Priority: Medium]** Bilingual switch — v1 system prompt의 영문 변형.
  - 입력: 위 prompt
  - 출력: `prompts/v1_*.en.md`
  - 의존성: 위 prompt
  - 참고: paper 작성 시 영어 trace 필요. 본문 기본은 한글.

- [x] **[Priority: Low]** Paper-writer tone review.
  - 입력: v1 prompt
  - 출력: 본 plan 파일에 review note 추가 — 학술 register / 임상 언어 톤의 적절성
  - 의존성: 위 prompt
  - 참고: 진단성 phrasing이 어디서 새는지 catch.

---

## Paper-writer tone review note (v1, 2026-05-17)

본 paper-writer review 는 `prompts/v1_*.md` 의 학술 register / 임상 언어 톤을 다음 관점에서 검증한다.

### ✅ 통과 항목

1. **Hedged language 일관성** — Light + Heavy 양 prompt 모두 "may", "might", "possibility of", "임상의 판단이 필요할 수 있다" 패턴 일관. 단정 어조 ban 명시.
2. **CLINICIAN-REVIEW marker 형식 일관성** — `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` exact string. Ban list 명시 (마취과 팀, 이형철 그룹, SNUH 마취과, Anesthesiology team, Prof. Lee HC group).
3. **Section header 영문 고정** — Heavy prompt 의 9-section name 이 영문 유지 → paper figure / trace 에서 그대로 사용 가능.
4. **Bilingual mirror 일관성** — EN variant 가 KR canonical 의 모든 정책을 한 줄도 빠뜨리지 않고 mirror (특히 ban list, hedging, mock_tier disclosure).
5. **Quantitative grounding 강조** — "정량 claim 은 tool 결과로 grounded" 정책이 양 prompt + guard block 에 명시. paper faithfulness 평가 (atomic-claim grounding, brief §11.1) 의 prompt-side 기반 마련.

### ⚠ 향후 review 필요 항목 (post-real-LLM)

1. **Token budget 검증** — Heavy prompt 의 walked-through example brief 가 "~750 tokens" 추정. 실 vLLM tokenizer (Llama-3.3 tokenizer) 로 측정 필요. 800 token 상한 위반 가능성 점검.
2. **Section 누락 빈도** — 9 section 중 일부 (특히 `[Similar trajectory]`) 가 tool 13 미구현으로 "TBD" 처리되는 경우, LLM 이 section 자체를 누락할 risk. plan_1.7 합류 후 재검증 필요.
3. **임상 phrasing 한국어 자연스러움** — "임상의의 판단이 필요할 수 있다" 패턴이 반복적으로 사용됨. 임상의 reviewer (이형철 교수님 그룹) 의 실제 사용 톤과의 정합성 검증 필요 — 자연스러운 韩 medical register 인지.
4. **Recommendation section 의 "조건문 phrasing" 경계** — `[Recommendations]` 가 "vasopressor 사용 여부는 임상의의 판단이 필요할 수 있다" 처럼 hedged 되어도, 임상의 입장에서 "결국 권고" 로 읽힐 risk 존재. plan_1.6 v2 (post-회의) 에서 더 엄격한 phrasing rubric 필요할 수 있음.
5. **Mock tier disclosure 가시성** — `mock_tier == "rule_based"` 시 `[Limitations]` 에 명시되지만, `[Risk evaluation]` section 본문에는 표기 없음. paper trace 의 faithfulness 평가 시 reviewer 가 "이 risk 가 mock 인지 real 인지" 의 출처를 분명히 보는 데 추가 표기가 필요할 가능성.
6. **English variant 의 임상 register** — Anesthesiology / critical care register 의 영문 phrasing 적절성. 향후 paper 작성 시 collaboration 임상의 (영문 권장) reviewer 와 sync 필요.

### Recommendation

v1 prompt 4 종은 prototype 시연 / plan_1.7 의 tool spec 작성 / 임상의 그룹 1차 review meeting 의 input 으로 충분히 사용 가능. v2 iteration trigger:
- 임상의 그룹 1차 review 후 phrasing 조정
- Real LLM (vLLM Llama) 합류 후 token budget / section 누락 실측 검증
- ADR-012/013/014 결정 후 surgery context / intervention-response phrasing 보강

---

## Definition of done

- `prompts/v1_light_shallow.md`, `prompts/v1_heavy_deep_brief.md`, `prompts/v1_clinical_fact_guard.md`, `prompts/v1_tool_description_style.md` 모두 commit됨
- Light prompt의 상태별 톤 예시 4개 검증됨
- 1개의 walked-through deep-brief 예시 (synthetic) 산출됨
- 양 prompt의 bilingual EN 변형 존재

## Data contracts established here

- **Prompt versioning 컨벤션** (`prompts/v{N}_<role>.md`) — Stage 3 평가에서 소비됨
- **Tool description style** (`plan_1.7_tool_spec.md`에서 소비됨)
