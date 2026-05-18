# VitalAgent — Obsidian 학습 노트

> 본 폴더는 **사용자가 LLM agent와 본 프로젝트의 코드를 이해할 수 있도록** 작성한 학습 자료다. Obsidian으로 열면 wikilink (`[[note]]`)가 작동한다.

## 시간이 부족하다면

딱 두 개만 읽으면 된다:

1. **[[00_프로젝트_개요]]** — 우리가 무엇을 만들고 있는가
2. **[[40_플랜/진행상황]]** — 지금까지 무엇이 만들어졌고, 다음에 무엇을 해야 하는가

이 두 문서는 의도적으로 plan_1.x 같은 코드 같은 참조 없이, 처음 읽는 사람도 이해할 수 있게 풀어 썼다.

## `plan_1.x` 라는 표기에 대해

본 repo 의 `.plans/stage1_preparation/plan_1.{1..8}_*.md` 는 Stage 1 의 작업 단위를 잘게 나눈 to-do 문서다. **이 번호를 외울 필요는 없다** — 어떤 plan 번호가 어떤 기능에 대응하는지 매핑은 [[40_플랜/진행상황]] 본문 끝의 "명명법" 절에 있다. Obsidian 노트 본문에서는 가능하면 capability 이름 (예: "Mock FM 3-tier", "21-tool spec") 으로 부른다.

---

## 진입점 (어디부터 읽으면 되나요)

처음이라면 다음 순서 권장:

1. **[[00_프로젝트_개요]]** — 우리가 무엇을 만들고 있는지 한 화면 요약
2. **[[10_기초/LLM_Agent_란]]** — LLM agent가 도대체 무엇인지부터
3. **[[10_기초/Tool_calling_과_Function_calling]]** — LLM이 tool을 호출한다는 뜻
4. **[[10_기초/LangGraph_와_StateGraph]]** — 우리가 쓰는 워크플로우 엔진
5. **[[10_기초/Pydantic_과_typed_state]]** — 코드에서 state를 typed로 다루는 법
6. **[[10_기초/Python_Protocol_과_runtime_checkable]]** — Mock FM swap의 핵심 기법

그리고 아키텍처:

7. **[[20_아키텍처/Dual_mode_architecture]]** — Shallow 30초 loop + Deep on-demand
8. **[[20_아키텍처/Mock_FM_3_Tier_전략]]** — 왜 mock FM이 3 tier로 나뉘는가
9. **[[20_아키텍처/21_Tool_Suite]]** — FM 7 + EMR 5 + Knowledge 2 + Auxiliary 2 + **Signal Access 5** (ADR-016)
10. **[[20_아키텍처/9_Section_Brief]]** — Deep mode 출력 구조
11. **[[20_아키텍처/Trigger_7_Rules]]** — Shallow → Deep 분기 결정 규칙
12. **[[20_아키텍처/데이터_누수_방지]]** — 시뮬레이션 시간 t 이후 데이터 금지

마지막으로 실제 코드:

13. **[[30_코드_워크스루/01_fm_layer]]** — FM 추상 (result_types / interface / factory)
14. **[[30_코드_워크스루/02_mock_stub]]** — Tier 1 stub (random)
15. **[[30_코드_워크스루/03_mock_rule_based]]** — Tier 2 rule-based
16. **[[30_코드_워크스루/04_state_clock_triggers]]** — state.py + sim_clock.py + triggers.py
17. **[[30_코드_워크스루/05_tools_layer]]** — envelope + fm_tools + emr_tools_stub + registry
18. **[[30_코드_워크스루/06_nodes_graph]]** — shallow_loop + deep_brief + graph
19. **[[30_코드_워크스루/07_llm_placeholder_와_plan_1_6]]** — placeholder LLM + 진짜 LLM 전환

---

## 폴더 구조 한눈에

```
obsidian/
├── README.md                          ← 지금 보는 파일
├── 00_프로젝트_개요.md                 ← 시작
├── 10_기초/                            ← LLM agent 입문
├── 20_아키텍처/                        ← 우리 시스템의 설계
├── 30_코드_워크스루/                   ← 실제 코드 한 줄씩
└── 40_플랜/                            ← 어디까지 왔는가
```

## Wikilink 사용 방법

본 문서들은 `[[파일이름]]` 형식으로 서로 연결된다. Obsidian에서:

- `[[10_기초/LLM_Agent_란]]` — 절대 경로
- `[[LLM_Agent_란]]` — Obsidian이 자동으로 찾음 (이름이 유일하면)

VS Code 같은 일반 에디터에서는 link가 안 눌리지만, 파일 경로를 직접 열면 된다.

## 한글 표기 컨벤션

본 obsidian 노트는 사용자가 LLM agent 도메인의 영어 용어를 처음 접한다는 가정 하에 작성되었다. 다음 패턴을 따른다.

- **기술 용어**는 한글 풀이 후 영문 병기: "**도구 사용 (tool use / tool calling)**"
- **코드 키워드 / 함수명 / 파일명**은 영문 그대로 백틱 안: `BiosignalFMInterface`, `predict_hypotension()`
- **임상 용어**는 한글 + 영문 병기: "**저혈압 (hypotension)**"
- **마커**는 영문 그대로: `[CLINICIAN-REVIEW]`, `[DECISION PENDING]`

자세한 규칙은 `docs/terminology.md` 참조.

## 본 노트와 코드의 관계

| Obsidian 노트 | 대응 코드 |
|---------------|-----------|
| `30_코드_워크스루/01_fm_layer.md` | `vitalagent/fm/{result_types,interface,factory}.py` |
| `30_코드_워크스루/02_mock_stub.md` | `vitalagent/fm/mock_stub.py` |
| `30_코드_워크스루/03_mock_rule_based.md` | `vitalagent/fm/mock_rule_based.py` |
| `30_코드_워크스루/04_state_clock_triggers.md` | `vitalagent/{state,sim_clock,triggers}.py` |
| `30_코드_워크스루/05_tools_layer.md` | `vitalagent/tools/*.py` |
| `30_코드_워크스루/06_nodes_graph.md` | `vitalagent/nodes/*.py` + `vitalagent/graph.py` |
| `30_코드_워크스루/07_llm_placeholder_와_plan_1_6.md` | `vitalagent/llm/placeholder.py` + `prompts/v1_*.md` |

코드가 바뀌면 노트도 같이 갱신해야 한다 (현재 노트는 Sprint 5 / 2026-05-17 기준).
