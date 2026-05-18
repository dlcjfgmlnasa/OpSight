# OpSight — Obsidian 학습 노트

> LLM agent 와 본 프로젝트 코드를 이해하기 위한 학습 자료. Obsidian 으로 열면 wikilink (`[[note]]`) 작동.

## 시간이 부족하다면

딱 두 개:

1. **[[00_프로젝트_개요]]** — 무엇을 만드는가
2. **[[40_플랜/진행상황]]** — 어디까지 왔고 다음은 무엇인가

이 두 문서는 plan_1.x 같은 코드 참조 없이 처음 읽는 사람도 이해할 수 있게 풀어 썼다.

## `plan_1.x` 표기에 대해

`.plans/stage1_preparation/plan_1.{1..8}_*.md` 는 Stage 1 작업 단위 to-do. **외울 필요 X** — 어떤 plan 이 어떤 capability 인지 매핑은 [[40_플랜/진행상황]] 의 "명명법" 절. Obsidian 노트 본문에서는 가능하면 capability 이름 (예: "Mock FM 3-tier", "21-tool spec") 사용.

---

## 진입점

처음이라면 순서:

1. **[[00_프로젝트_개요]]** — 한 화면 요약
2. **[[10_기초/LLM_Agent_란]]** — LLM agent 가 무엇인가
3. **[[10_기초/Tool_calling_과_Function_calling]]** — LLM 이 tool 을 호출한다는 뜻
4. **[[10_기초/LangGraph_와_StateGraph]]** — workflow 엔진
5. **[[10_기초/Pydantic_과_typed_state]]** — state typed 로 다루기
6. **[[10_기초/Python_Protocol_과_runtime_checkable]]** — Mock FM swap 의 핵심
7. **[[10_기초/dataclass_와_frozen]]** — 불변 결과 type

아키텍처:

8. **[[20_아키텍처/Dual_mode_architecture]]** — Shallow + Deep
9. **[[20_아키텍처/Mock_FM_3_Tier_전략]]** — 왜 mock 3 tier
10. **[[20_아키텍처/21_Tool_Suite]]** — FM 7 + EMR 5 + Knowledge 2 + Auxiliary 2 + Signal Access 5 (ADR-016)
11. **[[20_아키텍처/9_Section_Brief]]** — Deep 출력 구조
12. **[[20_아키텍처/Trigger_7_Rules]]** — Shallow → Deep 분기 규칙
13. **[[20_아키텍처/데이터_누수_방지]]** — `t` 이후 데이터 금지

코드:

14. **[[30_코드_워크스루/01_fm_layer]]** — FM 추상 (result_types / interface / factory)
15. **[[30_코드_워크스루/02_mock_stub]]** — Tier 1 stub
16. **[[30_코드_워크스루/03_mock_rule_based]]** — Tier 2 rule-based
17. **[[30_코드_워크스루/04_state_clock_triggers]]** — state + sim_clock + triggers
18. **[[30_코드_워크스루/05_tools_layer]]** — envelope + tool wrappers + registry
19. **[[30_코드_워크스루/06_nodes_graph]]** — shallow_loop + deep_brief + graph
20. **[[30_코드_워크스루/07_llm_placeholder_와_plan_1_6]]** — placeholder → 진짜 LLM

---

## 폴더 구조

```
obsidian/
├── README.md                          ← 지금 이 파일
├── 00_프로젝트_개요.md                 ← 시작
├── 10_기초/                            ← LLM agent 입문
├── 20_아키텍처/                        ← 시스템 설계
├── 30_코드_워크스루/                   ← 실제 코드
└── 40_플랜/                            ← 진행 상황
```

## Wikilink

- `[[10_기초/LLM_Agent_란]]` — 절대 경로
- `[[LLM_Agent_란]]` — Obsidian 이 자동으로 찾음 (이름 유일 시)

VS Code 같은 일반 에디터에서는 link 가 안 눌리지만 파일 경로 직접 열면 됨.

## 한글 표기 컨벤션

- **기술 용어** — 한글 풀이 후 영문 병기: "도구 사용 (tool use / tool calling)"
- **코드 키워드 / 함수명 / 파일명** — 영문 그대로 백틱: `BiosignalFMInterface`, `predict_hypotension()`
- **임상 용어** — 한글 + 영문 병기: "저혈압 (hypotension)"
- **마커** — 영문 그대로: `[CLINICIAN-REVIEW]`, `[DECISION PENDING]`

자세한 건 `docs/terminology.md`.

## 노트 ↔ 코드 매핑

| Obsidian 노트 | 대응 코드 |
|---------------|-----------|
| `30_코드_워크스루/01_fm_layer.md` | `opsight/fm/{result_types,interface,factory}.py` |
| `30_코드_워크스루/02_mock_stub.md` | `opsight/fm/mock_stub.py` |
| `30_코드_워크스루/03_mock_rule_based.md` | `opsight/fm/mock_rule_based.py` |
| `30_코드_워크스루/04_state_clock_triggers.md` | `opsight/{state,sim_clock,triggers}.py` |
| `30_코드_워크스루/05_tools_layer.md` | `opsight/tools/*.py` |
| `30_코드_워크스루/06_nodes_graph.md` | `opsight/nodes/*.py` + `opsight/graph.py` |
| `30_코드_워크스루/07_llm_placeholder_와_plan_1_6.md` | `opsight/llm/placeholder.py` + `prompts/v1_*.md` |

코드 변경 시 노트도 갱신 (현재 Sprint 5 / 2026-05-17 기준).
