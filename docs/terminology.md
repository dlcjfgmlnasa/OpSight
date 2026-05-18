# OpSight — 용어집 (Terminology)

> 본 문서는 OpSight 프로젝트의 모든 markdown 문서를 한글로 변환할 때
> 적용하는 **유일한 ground truth**다. 변환 시 의문이 생기면 본 파일을
> 우선 참조한다. 본 파일은 한글 변환 작업이 시작되기 *전에* 합의되어야
> 하며, 작업 중 누락된 용어는 발견 즉시 본 파일에 추가한다.
>
> Last updated: 2026-05-16. Scope: Korean translation pass of all `.md` docs.

---

## 1. 변환 원칙 (Translation Principles)

본 원칙은 사용자의 지시 8개 항목을 정리·고정한 것이다.

1. **기술 용어는 영문 유지**. 예: `LangGraph`, `Foundation Model`, `ReAct`, `API`, `tool`, `agent`, `Protocol`, `Pydantic`, `factory`, `runtime_checkable`.
2. **코드 식별자(파일명/변수/함수/경로)는 영문 유지**. 예: `BiosignalFMInterface`, `predict_hypotension`, `opsight/fm/interface.py`.
3. **일반 설명문은 한글로 작성**. 직역이 어색하면 의역 가능, 단 원 의미를 손상시키지 않는다.
4. **Section 헤더는 한글 + 영문 병기 허용**. 패턴은 §8 참조.
5. **임상 용어는 한글 + 영문 병기**. 예: "저혈압 (hypotension)". 본 표(§5)에 정의된 표기로 통일.
6. **Code block / YAML / JSON / 표 안의 코드 토큰은 절대 변경 X**.
7. **Marker는 영문 유지** (검색 가능성 보호). 예: `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`, `[DECISION PENDING]`.
8. **일관성 우선**: 같은 개념은 모든 문서에서 같은 한글 표기. 충돌 시 본 파일 표기를 정답으로 한다.

### 문체 (Voice / Register)

- 기본은 **합쇼체(는다/이다)** 평서문. 모든 instruction/policy/rule은 평서로 표현한다.
  - 예: "agent는 호출 시점에 본 plan을 반드시 다시 읽는다."
- **명령형 금지**: "…해라", "…해주세요", "…하세요" 형태는 사용하지 않는다. 대신 "…한다", "…수행한다", "…해야 한다"로 표현한다.
- **가능하면 주어 없는 평서**를 우선한다. 주어가 꼭 필요한 경우에만 명시한다.
  - 권장: "호출 시점마다 plan 파일을 다시 읽는다."
  - 비권장: "Agent는 호출 시점마다 plan 파일을 다시 읽어야 합니다."
- 1인칭 "본 agent" / "우리" 같은 자칭은 사용하지 않는다.
- "we" / "our" → "본 프로젝트는…" 또는 수동태로 우회하거나, 가능하면 생략.
- 영어식 문장 끝의 "we propose…", "we adopt…"는 "본 프로젝트는 … 채택한다" 또는 수동태 ("… 채택된다") 또는 생략.

---

## 2. 보존 영문 용어 — 절대 한글화 금지 목록 (Hard Preservation List)

다음은 **어떤 경우에도** 한글로 변환하지 않는다. 본 목록은 §3~§6보다 우선한다.

### 2.0 Hard preservation — 무조건 영문 유지

| 분류 | 예시 |
|------|------|
| 변수명 / 함수명 / 클래스명 / 모듈명 | `BiosignalFMInterface`, `predict_hypotension`, `StubBiosignalFM`, `create_fm`, `opsight.tools.registry`, `AgentState` |
| 파일 경로 / 디렉토리명 | `docs/project_brief.md`, `.plans/stage1_preparation/plan_1.1.5_mock_fm_stub.md`, `opsight/fm/interface.py`, `docs/notebooks/_cache/cases.csv`, `configs/fm/default.yaml` |
| Git / CLI 명령어 | `git status`, `pytest`, `python -m`, `pip install`, `.\.venv\Scripts\python.exe` |
| YAML / JSON 키, 환경변수 | `fm.implementation`, `case_id`, `sim_time_s`, `latency_sim_sec`, `noise_pct`, `$env:VITALDB_TOKEN` |
| Python 키워드 / 데코레이터 | `def`, `class`, `async`, `await`, `@runtime_checkable`, `@dataclass`, `from … import …` |
| Marker | `[CLINICIAN-REVIEW]`, `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`, `[DECISION PENDING]`, `[DECISION NEEDED]`, `[TODO]`, `[TODO: ...]`, `[CITATION NEEDED]`, `[FIGURE X]`, `[TABLE X]`, `<!-- TODO: ... -->` (§7 참조) |
| ADR 번호 | `ADR-001`, `ADR-011`, … |
| Section reference | `§3.5`, `§4`, `§4.1`, `§13.1`, … |
| VitalDB track 이름 | `SNUADC/ART`, `SNUADC/PLETH`, `SNUADC/ECG_II`, `Solar8000/ART_MBP`, `Solar8000/NIBP_MBP`, `BIS/EEG1_WAV`, `Primus/EXP_SEVO`, `Primus/INSP_SEVO`, `Primus/CO2`, `Orchestra/PPF20_CE`, `Orchestra/RFTN20_CE`, `EV1000/ART_MBP`, … (전체 목록은 `plan_1.1` 산출물 참조) |
| 모델명 | `Llama-3.1-8B`, `Llama-3.3-70B`, `Claude` (judge 용도), `Llama-3` 등 |
| Dataset 이름 | `VitalDB`, `K-MIMIC`, `MOVER`, `INSPIRE`, `PhysioNet`, `SNUH` |
| Journal / venue 이름 | `npj Digital Medicine`, `Nature Biomedical Engineering`, `IEEE TBME`, `IEEE JBHI`, `NeurIPS`, `ICML`, `MICCAI` |
| Code / YAML / JSON block | block 내부의 모든 토큰 (주석 포함; 단, 자연어 주석은 한글 OK) |

> Hard preservation 목록은 §3~§6의 어떤 패턴(영문 유지, 한글 병기 등)보다도 우선한다. 즉, 본문에 `predict_hypotension` 함수명이 등장하면 "저혈압 예측 (predict_hypotension)" 식으로 풀어 쓰지 않고 `predict_hypotense` 백틱 영문 그대로 둔다.

#### VitalDB Track Names — 영문 절대 유지 (Hard preservation 보강)

VitalDB의 track 식별자는 grep 호환성과 코드 일치성을 위해 **어떤 경우에도 한글화하지 않는다**. 첫 등장 시 채널의 임상 의미를 *보조 한글 풀이*로 추가하는 것은 허용되나, 영문 채널명 자체는 변경되지 않는다.

**Device prefix (영문 100% 유지)**

| Prefix | 장비 |
|--------|------|
| `Solar8000/` | patient monitor (수술실 표준 모니터) |
| `SNUADC/` | waveform digitizer (raw waveform 수집) |
| `Primus/` | anesthesia machine (마취기) |
| `Orchestra/` | drug infusion pump (약물 주입 펌프) |
| `BIS/` | BIS monitor |
| `EV1000/` | advanced hemodynamic monitor |
| (기타) | 발견 시 즉시 본 표에 추가 |

**Channel name 예시 (영문 100% 유지)**

`Solar8000/ART_MBP`, `Solar8000/NIBP_MBP`, `Solar8000/HR`, `Primus/EXP_SEVO`, `Primus/INSP_SEVO`, `Primus/CO2`, `Primus/AWP`, `SNUADC/ART`, `SNUADC/PLETH`, `SNUADC/ECG_II`, `BIS/EEG1_WAV`, `BIS/BIS`, `Orchestra/PPF20_CE`, `Orchestra/RFTN20_CE`, `EV1000/ART_MBP`, `Solar8000/FEM_MBP`, …

**보조 한글 풀이 (선택, 첫 등장에만 — 영문 변경 X)**

- 예: `Solar8000/ART_MBP` (invasive arterial mean blood pressure) — 영문 채널명은 그대로
- 예: `Primus/EXP_SEVO` / `Primus/INSP_SEVO` (sevoflurane, 호기 / 흡기) — 영문 채널명은 그대로

**금지**

- 채널명 일부를 한글화 (예: `Solar8000/동맥압_MBP`) — **금지**.
- 채널명을 백틱 없이 평문에서 사용 — **지양** (`Solar8000/ART_MBP`와 같이 백틱 안에 둔다).

### 2.1 보존 영문 용어 — 프레임워크 / 기술 (Tech Stack)

다음 용어는 영문 그대로 유지한다. 별도 한글 병기 불필요.

| 분류 | 용어 |
|------|------|
| 프레임워크 | `LangGraph`, `LangChain`, `LangSmith`, `vLLM`, `PyTorch`, `Pydantic`, `pandas`, `numpy`, `scipy`, `pytest`, `nbformat`, `ruff` |
| LLM | `Llama-3.1-8B`, `Llama-3.3-70B`, `Claude` (judge 용도) |
| API / lib | `vitaldb` (Python library), `vitaldb.find_cases`, `vitaldb.load_case`, `vitaldb.load_clinical_data`, `https://api.vitaldb.net/cases`, `https://api.vitaldb.net/trks` |
| 데이터 형식 | `parquet`, `sqlite`, `CSV`, `JSON`, `YAML`, `Pydantic`, `TypedDict`, `dataclass`, `JSON schema`, `nbformat` |
| 패턴 / 아키텍처 | `Protocol`, `runtime_checkable`, `factory`, `state schema`, `node`, `edge`, `StateGraph` |
| 양자화 / 추론 | `4-bit`, `quantization`, `streaming`, `vLLM` |
| 일반 ML | `attention`, `transformer`, `embedding`, `encoder`, `decoder`, `MoE`, `RoPE`, `GQA`, `MHA`, `MQA`, `GLU`, `RMSNorm`, `pretraining`, `downstream task`, `checkpoint`, `forward pass`, `inference`, `latency`, `throughput`, `epoch`, `tokens`, `frozen`, `freeze` |

#### `frozen` / `freeze` 처리 규칙

- `frozen` (형용사, 가중치 동결 상태) — 첫 등장: "가중치 동결된 (frozen)" 풀이. 이후: `frozen` 영문 단독.
  - 예: "가중치 동결된 backend (frozen backend)로 활용" → 이후 "frozen backend"
- `freeze` (동사) — 첫 등장: "동결한다 (freeze)" 풀이. 이후: 한글 또는 영문 (문맥 자연스러운 쪽).
  - 예: "Stage 2 시작 시점에 FM 가중치를 동결한다 (freeze)" → 이후 "동결" 또는 "freeze"
| 평가 / 통계 | `AUROC`, `AUPRC`, `sens@spec`, `Cohen's κ`, `Likert`, `inter-rater agreement`, `p-value`, `CI` (신뢰구간) |
| 도구 / 시스템 | `tool`, `agent`, `subagent`, `system prompt`, `tool description`, `tool calling`, `JSON schema`, `state`, `trace`, `cooldown`, `trigger`, `mock`, `stub`, `interface`, `protocol`, `factory` |
| 디자인 산출물 | `ADR` (Architecture Decision Record), `master_plan`, `plan_*`, `findings`, `notebook` |

> "agent"와 "tool"은 매우 빈번하게 등장하므로 한글 변환 시 매번 병기하지 않는다. 첫 등장에서 한 번만 "agent (에이전트)"처럼 풀어주고, 이후엔 영문만 사용한다.

---

## 3. 보존 영문 용어 — 신호 / 데이터 (Signal & Data)

| 약어 | 의미 (참고용, 본문에서는 영문 약어만 사용) |
|------|---------------------------------------------|
| `ECG` | electrocardiogram, 심전도 |
| `EEG` | electroencephalogram, 뇌파 |
| `EMG` | electromyogram, 근전도 |
| `PPG` | photoplethysmogram, 광용적맥파 |
| `ABP` | arterial blood pressure, 동맥압 (waveform) |
| `MAP` | mean arterial pressure, 평균동맥압 |
| `SBP / DBP` | systolic / diastolic blood pressure |
| `NIBP` | non-invasive blood pressure, 비침습 혈압 (cuff) |
| `CVP` | central venous pressure |
| `PAP` | pulmonary artery pressure |
| `ICP` | intracranial pressure |
| `HR` | heart rate |
| `SpO2` | oxygen saturation |
| `BIS` | bispectral index |
| `EtCO2` | end-tidal CO2 |
| `RFTN / RFTN20` | remifentanil (Orchestra/RFTN20_*) |
| `PPF / PPF20` | propofol (Orchestra/PPF20_*) |
| `SEVO` | sevoflurane (Primus/EXP_SEVO, INSP_SEVO) |
| `K-MIMIC` | dataset name |
| `VitalDB` | dataset name |
| `MOVER`, `INSPIRE` | dataset names (future external validation) |
| `ASA` | American Society of Anesthesiologists physical status |
| `BMI` | body mass index |
| `EMR` | electronic medical record |
| `ICU` | intensive care unit |
| `IRB` | institutional review board |
| `PoC` | Proof-of-Concept (개념 증명). 본 PoC = 본 프로젝트의 현 단계 (Month 1–10) 산출물 전체. 첫 등장 시 "PoC (Proof-of-Concept, 개념 증명)", 이후 `PoC` 약어 단독. |

신호 채널 이름(`SNUADC/ART`, `Solar8000/ART_MBP`, `Primus/EXP_SEVO` 등)은 백틱 안에 영문 그대로 표기한다.

---

## 4. 일반 용어 한글 변환 (General Terms)

문서 전반에서 자주 등장하는 일반 표현의 한글 변환을 통일한다.

| English | 한글 (표준) | 비고 |
|---------|-------------|------|
| Goal | 목표 | section header에 자주 등장 |
| Rationale | 근거 (Rationale) | ADR 표준 헤더 |
| Context | 배경 (Context) | ADR / brief 표준 |
| Decision | 결정 (Decision) | ADR |
| Alternatives Considered | 검토한 대안 (Alternatives Considered) | ADR |
| Consequences | 결과 / 영향 (Consequences) | ADR |
| Positive / Negative | 긍정적 영향 / 부정적 영향 | ADR Consequences 하위 |
| Risk / Risks | 위험 (Risk) | risk register |
| Mitigation | 완화 / 대응책 | risk register |
| Status | 상태 | plan / ADR |
| Owner | 담당 | plan |
| Assist | 보조 | plan |
| Reviewer | 검토자 | plan |
| Tasks | 작업 (Tasks) | plan |
| Inputs | 입력 | plan task |
| Outputs | 출력 | plan task |
| Dependencies | 의존성 | plan task |
| Note / Notes | 참고 | plan task |
| Definition of done | 완료 정의 (Definition of done) | plan |
| Acceptance Criteria | 완료 기준 (Acceptance Criteria) | master_plan |
| Critical Path | Critical Path | 영문 유지 (PM 용어) |
| Workflow | 작업 흐름 (Workflow) | agent charter |
| Workstream | 작업 트랙 | master_plan |
| Roadmap | 로드맵 | master_plan |
| Mission | 미션 | master_plan |
| Scope IN / OUT | 담당 영역 (Scope IN) / 비담당 영역 (Scope OUT) | charter |
| Charter | 헌장 (Charter) 또는 영문 유지 | agent definition 본문에서는 영문 유지 권장 |
| Persistent Agent Memory | Persistent Agent Memory | 영문 유지 (시스템 prompt block 명칭) |
| Single Source of Truth (SoT) | 단일 진실 원천 (Single Source of Truth, SoT) | brief / master_plan |
| Cross-reference | 상호 참조 (Cross-reference) | 검증 절 |
| Out of scope | 본 작업의 범위 밖 | 결정 명세 |
| Will be detailed when | 상세 작성 시점 | stage placeholder |
| Tentative | 잠정 | placeholder |
| Placeholder | placeholder | 영문 유지 |
| Status: PLACEHOLDER | 상태: PLACEHOLDER | placeholder |
| 조건문 (conditional) — 사용 패턴 | Clinical Fact Guard 문맥. 단정형 회피 → 조건/추세/가능성 형태. 예: 단정 "환자는 sepsis다" 회피, 조건 "lactate 상승 추세를 보일 때 sepsis 가능성을 고려한다" 권장. | Hard rule §13.1 적용 시 자주 등장 |
| Open question | 미결 사항 (Open question) | findings |
| Surprise / Surprises | 놀라운 발견 | findings |
| Reproducibility | 재현성 (Reproducibility) | findings |
| Bottom line | 핵심 결론 (Bottom line) | findings |
| Verdict | 판정 | findings |
| Match / Matches | 일치 | findings |
| Differs / Review required | 차이 있음 / 검토 필요 | findings |
| Reference / References | 참조 (References) | ADR 등 |
| TBD | TBD | 영문 유지 |
| N/A | N/A | 영문 유지 |
| optional | 선택 (optional) | plan |
| mandatory | 필수 (mandatory) | plan |
| current / next / previous stage | 현재 / 다음 / 이전 stage | master_plan |
| Predecessor | 선행 (Predecessor) | stage README |
| Hard rule | 강제 규칙 (Hard rule) | brief §13 |
| Guardrail / Guard | 가드 (Guard) | hallucination guard 등 |
| Best practice | best practice | 영문 유지 |
| End-to-end | end-to-end | 영문 유지 |
| Side-by-side | 병행 (side-by-side) | ADR 마이그레이션 |
| Smoke test | smoke test | 영문 유지 (테스트 용어) |
| Integration test | 통합 테스트 (integration test) | 테스트 |
| Unit test | 단위 테스트 (unit test) | 테스트 |

---

## 5. 임상 용어 (Clinical Terms)

### 5.0 병기 빈도 규칙 (Frequency Rule)

- **문서 내 첫 등장 시**: "한글 (영문, 약어)" 병기.
  - 예: "수술 중 저혈압 (intraoperative hypotension, IOH)"
  - 예: "급성 신손상 (postoperative acute kidney injury, PO-AKI)"
- **같은 문서의 두 번째 등장부터**: 영문 약어 또는 한글 단독 중 문맥에 자연스러운 쪽을 선택.
  - 예: "이후 IOH는 …" / "이후 저혈압이 …"
- **다른 문서로 넘어가면**: 그 문서에서 다시 "첫 등장" 처리(병기 다시 적용).
- **표 안 / 짧은 항목 리스트**: 공간 제약 시 영문 약어 단독 허용. 단 같은 표 안에서 일관되게.
- **paper draft**: paper-writer가 정식 표기로 별도 관리(첫 등장 병기 → 이후 영문 약어가 학술적 관행).

### 5.1 임상 용어 표

본 표는 한글 + 영문 병기 표준을 고정한다. 위 §5.0 빈도 규칙에 따라 적용한다.

| 한글 (표기) | English | 비고 |
|-------------|---------|------|
| 비심장 (non-cardiac) | non-cardiac | brief §1 / cohort 분류 핵심 용어. 첫 등장 시 "비심장 (non-cardiac)". 복합어는 전체구 병기 — 예: "비심장 주요 수술 (non-cardiac major surgery)". 이후 영문 또는 한글 (문맥). |
| 저혈압 (hypotension) | hypotension | event definition 핵심 용어 |
| 고혈압 (hypertension) | hypertension | |
| 부정맥 (arrhythmia) | arrhythmia | downstream task 1 |
| 심근경색 (MI) | myocardial infarction (MI) | downstream task 2 |
| 심정지 (cardiac arrest) | cardiac arrest | downstream task 4 |
| 패혈증 (sepsis) | sepsis | downstream task 5 |
| 사망률 (mortality) | mortality | downstream task 6 |
| 급성 신손상 (PO-AKI) | postoperative acute kidney injury (PO-AKI) | downstream task 7 |
| 기관발관 (extubation) | extubation | downstream task 8 |
| 마취 (anesthesia) | anesthesia | |
| 마취제 (anesthetic) | anesthetic | drug 카테고리 |
| 마취과 의사 / 마취과 임상의 | anesthesiologist | 평가자 (이형철 교수님 그룹) |
| 임상의 (clinician) | clinician | 일반 |
| 환자 (patient) | patient | |
| 시술 / 수술 (surgery) | surgery | |
| 수술기 (perioperative) | perioperative | brief / paper |
| 술전 (preoperative) | preoperative | EMR baseline |
| 술중 (intraoperative) | intraoperative | brief tagline 핵심 |
| 술후 (postoperative) | postoperative | outcome 평가 |
| 유도기 (induction) | induction phase | surgery phase |
| 유지기 (maintenance) | maintenance phase | surgery phase |
| 회복기 / 각성기 (emergence) | emergence phase | surgery phase |
| 혈역학 (hemodynamics) | hemodynamics | brief tagline 핵심 |
| 혈역학적 (hemodynamic) | hemodynamic | |
| 신호 품질 (signal quality) | signal quality | quality-aware |
| 모달리티 (modality) | modality | 의도적으로 음차 — "modality"는 영문 유지하되 첫 등장 시 "모달리티 (modality)"로 |
| 침습 (invasive) | invasive | 침습 동맥압 등 |
| 비침습 (non-invasive) | non-invasive | NIBP |
| 카프노그래피 (capnography) | capnography | EtCO2 |
| 약물 (drug) | drug | |
| 혈관활성 약물 (vasoactive drug) | vasoactive drug | tool 9. 광의 — vasoactive 약물 일반. |
| 혈관수축제 (vasopressor) | vasopressor | 협의 — 혈관수축 약물 (norepinephrine, phenylephrine 등). ADR-012 Tier 4 T4.1. |
| 진통제 (analgesic) | analgesic | 약물 분류 — remifentanil. brief §4.3. |
| 최면제 (hypnotic) | hypnotic | 약물 분류 — propofol, sevoflurane. brief §4.3. |
| 근이완제 (muscle relaxant) | muscle relaxant | 약물 분류 — rocuronium. brief §4.3. |
| 정질액 (crystalloid) | crystalloid | 수액 분류 — ADR-012 Tier 4 T4.2 |
| 교질액 (colloid) | colloid | 수액 분류 — ADR-012 Tier 4 T4.2 |
| MAC (최소 폐포 농도) | Minimum Alveolar Concentration (MAC) | 흡입 마취제 dose 단위. 첫 등장 시 "MAC (Minimum Alveolar Concentration)", 이후 `MAC`. |
| 혈역학 상태 (hemodynamic state) | hemodynamic state | ADR-014 Tier 0 #14 — supervised classification 출력 |
| 마취 상태 (anesthesia state) | anesthesia state | ADR-014 Tier 0 #15 — hybrid 출력 (depth-of-anesthesia 분류) |
| 수술 단계 (surgical phase) | surgical phase | ADR-014 Tier 0 #16 — `plan_1.5_surgery_context.md`의 phase enum (induction / maintenance / emergence) |
| 저산소증 (hypoxemia) | hypoxemia | ADR-012 Tier 2 T2.2 — SpO2 < 90% |
| 서맥 (bradycardia) | bradycardia | ADR-012 Tier 2 T2.1 — HR < 50 |
| 빈맥 (tachycardia) | tachycardia | ADR-012 Tier 2 T2.1 — HR > 120 |
| 출혈 (bleeding) | bleeding | ADR-012 Tier 2 T2.3 — bleeding suspicion composite |
| 노르에피네프린 (norepinephrine) | norepinephrine | vasoactive |
| 페닐에프린 (phenylephrine) | phenylephrine | vasoactive |
| 에페드린 (ephedrine) | ephedrine | vasoactive |
| 프로포폴 (propofol) | propofol | anesthetic — Orchestra/PPF20 |
| 레미펜타닐 (remifentanil) | remifentanil | analgesic — Orchestra/RFTN20 |
| 세보플루레인 (sevoflurane) | sevoflurane | inhaled — Primus/EXP_SEVO |
| 수액 (fluid) | fluid | tool 10 |
| 수혈 (blood transfusion) | blood transfusion | tool 10 |
| 예후 (prognosis) | prognosis | Clinical Fact Guard에서 단정 금지 대상 |
| 진단 (diagnosis) | diagnosis | Clinical Fact Guard에서 단정 금지 대상 |
| 코호트 (cohort) | cohort | |
| 검증 (validation) | validation | internal / external |
| 외부 검증 (external validation) | external validation | stage 3 |
| 베이스라인 (baseline) | baseline | 비교 모델 |
| 알람 (alarm) | alarm | false-alarm rate |
| 오경보 / 거짓 경보 (false alarm) | false alarm | evaluator rubric |
| 환각 (hallucination) | hallucination | LLM 문맥 |
| 불확실성 (uncertainty) | uncertainty | quality-aware 핵심 |
| 활력 징후 (vital signs) | vital signs | tool 17 `get_current_vitals` 출력 — MAP / HR / RR / SpO₂ / EtCO₂ 등 |
| 심박변이도 (HRV) | heart rate variability (HRV) | tool 19 `assess_variability` 의 HR metric. 약어 `HRV` 영문 유지 |
| SDNN | SDNN | HRV metric — standard deviation of NN intervals. **영문 유지** |
| RMSSD | RMSSD | HRV metric — root mean square of successive differences. **영문 유지** |
| LF/HF 비 | LF/HF ratio | HRV metric — low-frequency / high-frequency power ratio. **영문 유지** |
| 혈압 변동성 (BPV) | blood pressure variability (BPV) | tool 19 의 MAP / ABP metric. 약어 `BPV` 영문 유지 |
| ARV (평균 실측 변동) | average real variability (ARV) | BPV 의 한 metric. **영문 유지** |
| 박출량 변이 (SVV) | stroke volume variation (SVV) | tool 19 의 PPG metric. 약어 `SVV` 영문 유지 |
| 기저값 (baseline) | baseline | tool 20 `compare_to_baseline` 의 기준점. 별도 의미 — model "베이스라인" (lit. comparator) 과 구분 (terminology §5.1 별 entry 참고) |
| 정상 범위 (normal range) | normal range | tool 17–21 결과의 임상 해석 보조 표현. 단정 phrasing 아님 — "정상 범위 내" 같은 형태 |
| 현재 상태 (current state) | current state | **3-layer 의미 구분** (혼동 회피): (1) **ADR-014 "Current State Assessment"** = 학습된 supervised head (Tier 0 capability #14–16). (2) **ADR-016 "Signal Access Tools"** = deterministic tool layer (tool 17–21) — 본 카테고리는 명명 충돌 회피를 위해 *Signal Access* 로 부른다 (terminology §6.0 참조). (3) **함수명 `get_current_vitals` / `summarize_current_state`** = 함수 의미 그대로. 위 3 layer 는 의미적으로 인접하나 구현 layer 가 다름. |

---

## 6. 프로젝트 고유 표기 (Project-specific Conventions)

본 §6는 §5.0 빈도 규칙을 따른다 (문서 내 첫 등장 시 병기, 이후 영문 또는 한글 단독).

### 6.0 Tool 카테고리 표기 (Tool category naming) — ADR-016 추가

| 표기 | 비고 |
|------|------|
| FM-based (1–7) | 영문 유지 |
| EMR (8–12) | 영문 유지 |
| Knowledge / Comparative (13–14) | 영문 유지 |
| Auxiliary (15–16) | 영문 유지 |
| **Signal Access (17–21)** | **영문 유지** — ADR-016 신설. **명명 정책**: ADR-014 의 "Current State Assessment" (학습 capability) 와 명칭 충돌 회피를 위해 본 카테고리는 일관되게 **"Signal Access"** 로 부른다 ("Current State Tools" 표기 사용 금지). Tool 함수명 (`get_current_vitals`, `describe_signal`, `assess_variability`, `compare_to_baseline`, `summarize_current_state`) 은 *함수 의미* 를 반영하므로 그대로 유지. |

### 6.1 모달리티 / 품질 / 수술 인지 계열 (modality / quality / surgery family)

| 표기 (첫 등장) | 영문 원본 | 이후 표기 | 비고 |
|----------------|-----------|-----------|------|
| 모달리티 (modality) | modality | `modality` 영문 단독 | 의도적 음차 |
| 모달리티 비의존 (modality-agnostic) | modality-agnostic | `modality-agnostic` 영문 | brief Core Characteristic #2 |
| 신호 품질 인지 (quality-aware) | quality-aware | `quality-aware` 영문 | Core Characteristic #3 |
| 수술 인지 (surgery-aware) | surgery-aware | `surgery-aware` 영문 | Core Characteristic #4 |
| Universal | universal | 영문 그대로 | Core Characteristic #1. 한글 풀이 없음. |

### 6.2 시스템 모드 / 운영 표기 (System modes / operational terms)

| 표기 | 영문 원본 | 비고 |
|------|-----------|------|
| 이중 모드 (dual-mode) | dual-mode | 첫 등장 시 병기, 이후 `dual-mode` 영문. brief §6 핵심. |
| Shallow 모드 | shallow mode | **한글 풀이 없음** — 시스템 고유명사. "Shallow"는 영문, "모드"만 한글. |
| Deep 모드 | deep mode | **한글 풀이 없음** — 시스템 고유명사. |
| Trigger | trigger | **영문 유지** — 한글 변환 없음. brief §6.3 deep-mode trigger 7개. |
| 시뮬레이션된 실시간 (simulated real-time) | simulated real-time | 첫 등장 시 병기, 이후 `simulated real-time` 영문. brief §10. |
| 브리프 (brief) | brief | deep mode 9-section 출력물. 이후 "브리프" 음차 또는 `brief` 영문. |

### 6.3 핵심 산출물 / 모델 표기 (Core artifacts / models)

| 표기 | 영문 원본 | 비고 |
|------|-----------|------|
| Foundation Model (FM) | foundation model | 영문 유지 |
| Mock FM (Tier 1/2/3) | mock FM | ADR-011 핵심 용어. 영문 유지. |
| Light LLM / Heavy LLM | light LLM / heavy LLM | 영문 유지. Light = `Llama-3.1-8B`, Heavy = `Llama-3.3-70B`. |

### 6.4 거버넌스 / 평가 표기 (Governance / evaluation)

| 표기 | 영문 원본 | 비고 |
|------|-----------|------|
| 단일 진실 원천 (Single Source of Truth, SoT) | Single Source of Truth | 첫 등장 시 병기, 이후 `SoT` 약어 |
| 임상 평가 (clinical evaluation) | clinical evaluation | stage 4 |
| 자동 평가 (automated evaluation) | automated evaluation | stage 3 |
| 데이터 누수 (data leakage) | data leakage | hard rule §13.2 |
| 임상 사실 가드 (Clinical Fact Guard) | Clinical Fact Guard | hard rule §13.1. 헤더 패턴: "## ⚠️ Clinical Fact Guard (임상 사실 가드)" |

### 6.5 임상 협력자 호칭 (Clinical collaborator naming) — **정식 표기 + Ban list**

| 항목 | 표기 |
|------|------|
| **한글 정식 표기 (project-wide)** | **이형철 교수님 그룹** |
| **영문 paper 표기 (잠정)** | Vital Group, Department of Anesthesiology and Pain Medicine, Seoul National University Hospital |
| **공식 영문 표기 확정 상태** | 잠정 — `[CLINICIAN-REVIEW: 이형철 교수님 그룹의 공식 영문 표기 확인 필요]` |
| **사용 위치** | brief, master_plan, clinical-evaluator charter, paper Methods §, all `[CLINICIAN-REVIEW]` markers |

#### Ban list — **사용 금지 표기**

다음 표기는 어떤 문서에서도 사용하지 않는다. 발견 시 즉시 "이형철 교수님 그룹"으로 교체한다.

| 금지 표기 | 사유 |
|-----------|------|
| 마취과 팀 | 불특정 — 어느 마취과인지 모호 |
| 이형철 그룹 | 호칭 결여 ("교수님" 빠짐) |
| SNUH 마취과 | 부서명만 — 그룹 단위 명확성 결여 |
| Prof. Lee HC group | 영문이지만 비공식. paper draft에서도 §6.5의 정식 영문 표기를 사용 |
| Anesthesiology team | 동일 사유 |

#### 기타 임상 호칭

| 표기 | 비고 |
|------|------|
| 마취과 의사 / 마취과 임상의 (anesthesiologist) | 일반 호칭. 그룹 지칭 시 위 정식 표기 사용. |
| 임상의 (clinician) | 마취과 외 영역까지 포함하는 일반 호칭 |

### 6.6 기관 / Venue / Dataset 표기

- `SNUH` = Seoul National University Hospital. 한글 풀이가 필요한 경우 "서울대학교병원 (SNUH)" 첫 등장 후 `SNUH` 영문 약어.
- `VitalDB`, `K-MIMIC`, `MOVER`, `INSPIRE`, `PhysioNet` — 영문 그대로.
- `npj Digital Medicine`, `Nature Biomedical Engineering`, `IEEE TBME`, `IEEE JBHI` 등 venue 이름 — 영문 그대로.

### 6.7 Tagline 표기

OpSight의 영문 tagline은 paper / venue 제출용 정체성 문구이므로 **영문 원문 유지**가 기본이다. 한글 변환 시 임팩트 손실 가능성이 높다.

**표기 규칙**

| 등장 시점 | 표기 |
|-----------|------|
| **문서 내 첫 등장** | 영문 tagline 원문 + **별도 한글 요약 1–2문장** 병기 |
| 이후 등장 | 영문 tagline 단독 또는 `OpSight` 단독 |

**영문 tagline (정식)**

> *A universal, modality-agnostic, quality-aware LLM agent for real-time intraoperative hemodynamic reasoning, powered by a cross-domain pretrained multimodal biosignal foundation model.*

**한글 요약 예시 (참고 — 문서 맥락에 맞춰 1–2문장으로 paraphrase)**

> 모든 비심장 주요 수술에 대해 가용한 모달리티로 작동하며, 신호 품질을 인식하여 술중 혈역학 reasoning을 시뮬레이션된 실시간으로 수행하는 범용 LLM agent.

**금지**

- 영문 tagline을 한글로 *대체* — 금지.
- 영문 tagline 단어 일부만 한글화 — 금지.

### 6.8 Downstream task suite 표기 (ADR-012 / -013 / -014)

본 표기는 **모두 영문 유지**가 기본이다. 한글 풀이는 첫 등장에서만 선택적으로 추가하며, 강제는 아니다.

| 표기 | 비고 |
|------|------|
| `Tier 0` / `Tier 1` / `Tier 2` / `Tier 3` / `Tier 4` | 영문 + 숫자 유지. 한글 변환 X. |
| Tier 0 — Current State Assessment | 영문 유지. 한글 풀이 (현재 상태 평가)는 ADR-014 §Context에서만 사용. |
| Tier 1 — Acute Event | 영문 유지 |
| Tier 2 — Surgery-specific Event | 영문 유지 |
| Tier 3 — Generative / Forecasting | 영문 유지 |
| Tier 4 — Intervention Response | 영문 유지. ADR-013 핵심 용어. |
| surgery-specific downstream | 영문 유지. brief / paper에서 "본 논문 FM의 general downstream과 분리된 OR-specific 13–16 capability". |
| Vasopressor response / Fluid response / Anesthetic change response | Tier 4 sub-task 이름 — 영문 유지. |
| Hemodynamic state classification | Tier 0 #14. 영문 유지. (한글 출처: 혈역학 상태 — §5.1) |
| Anesthesia state assessment | Tier 0 #15. 영문 유지. (한글 출처: 마취 상태 — §5.1) |
| Surgical phase recognition | Tier 0 #16. 영문 유지. (한글 출처: 수술 단계 — §5.1) |
| weak label | 영문 유지. 첫 등장 시 "weak label (약한 라벨)" 풀이 권장. |
| Confounding | 영문 유지. ADR-013 §"Confounding 처리 원칙"에서 사용. 한글 풀이는 "교란 요인 (confounding)" 첫 등장 시. |
| Phase 1 (PoC) / Phase 2 (future) | 본 PoC 범위 vs 후속. 영문 유지. (NRF 도전형 2–3년차 follow-up은 brief §10에 이미 존재.) |

---

## 7. Marker (보존 — 영문 그대로)

본 marker들은 grep 검색 가능성을 위해 영문 그대로 유지한다.

| Marker | 용도 |
|--------|------|
| `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` | 임상 사실 단정 가드 (Hard rule §13.1) |
| `[CLINICIAN-REVIEW: 이형철 교수님 그룹의 공식 영문 표기 확인 필요]` | 그룹 공식 영문 표기 확정 대기 (§6.5) |
| `[CLINICIAN-REVIEW]` | 위의 짧은 형식 |
| `[DECISION PENDING]` | cohort 결정 등 임상의 결정 대기 |
| `[DECISION NEEDED]` | 결정 필요 (포괄적) |
| `[TODO]` | 후속 작업 |
| `[TODO: ...]` | 구체 후속 작업 |
| `[CITATION NEEDED]` | paper-writer 미확정 citation |
| `[FIGURE X]`, `[TABLE X]` | paper figure/table placeholder |
| `<!-- TODO: ... -->` | brief 내 TODO 마커 (HTML 주석 형식) |

Marker 안의 내용이 한글일 수 있다(예: 이형철 교수님 그룹). marker **자체**는 영문/대괄호 그대로.

---

## 8. Section 헤더 패턴 (Section Header Patterns)

세 가지 표준 패턴 중 하나를 일관되게 사용한다.

### Pattern A — 한글 우선 (Korean-first)
```
## 1. 프로젝트 정체성 (Project Identity)
## 2. 데이터셋 — VitalDB (Dataset)
## 3. Mock FM 전략 (Mock FM Strategy)
```
**적용 대상**: `docs/project_brief.md`, `.plans/master_plan.md`, `docs/terminology.md`, `docs/findings/*.md`, `docs/analysis/*.md`.

### Pattern B — 영문 유지 (Tech header)
```
## Tasks
## Definition of done
## Acceptance Criteria
## Risk Register
## Status Log
```
**적용 대상**: `.plans/stage*/plan_*.md` (표준 plan 골격), `docs/notebooks/*.ipynb` markdown cells, `.plans/stage*/README.md` placeholder.

### Pattern C — 영문 우선 + 한글 보조
```
## Workflow (작업 흐름)
## Scope IN (담당 영역)
## Scope OUT (비담당 영역)
## Rationale (근거)
```
**적용 대상**: `.claude/agents/*.md` (agent charter), `docs/decisions/ADR-*.md`.

### 패턴 매핑 표

| 디렉토리 / 파일 | 패턴 |
|-----------------|------|
| `CLAUDE.md` | A |
| `docs/project_brief.md` | A |
| `docs/terminology.md` (본 파일) | A |
| `docs/decisions/ADR-*.md` | C |
| `.plans/master_plan.md` | A |
| `.plans/stage*/plan_*.md` | B |
| `.plans/stage*/README.md` (placeholder, 짧은 prose 위주) | A |
| `.claude/agents/*.md` | C |
| `docs/findings/*.md` | A |
| `docs/analysis/*.md` | A |
| `docs/notebooks/*.ipynb` markdown cells | B |

> 패턴 선택은 문서 단위로 결정한다. 한 문서 안에서 패턴을 섞지 않는다.

---

## 9. 표 컬럼 헤더 표기 (Table Column Headers)

자주 등장하는 표 컬럼은 다음으로 통일.

| 자주 쓰는 컬럼 | 표기 |
|----------------|------|
| Plan | Plan |
| Lead → Assist | 담당 → 보조 |
| Status | 상태 |
| Owner | 담당 |
| Stage | Stage |
| Months | 기간 (months) |
| Core deliverable | 핵심 산출물 |
| Goal | 목표 |
| Input / Output | 입력 / 출력 |
| Verdict | 판정 |
| Risk | 위험 |
| Mitigation | 대응책 |
| Note | 참고 |
| Description | 설명 |

---

## 10. 자주 쓰는 문구 (Common Phrases)

영어식 표현 → 한글 표준.

| English | 한글 표준 |
|---------|-----------|
| At the start of every invocation | 호출 시점마다 |
| Read fresh every time | 매번 다시 읽는다 |
| Update the plan file | plan 파일을 갱신한다 |
| Mark as done | 완료(`[x]`)로 표시한다 |
| In parallel to | …와 병행하여 |
| Must not | 반드시 …하지 않는다 / 금지 |
| Must | 반드시 …한다 |
| Should | …해야 한다 |
| May | …할 수 있다 |
| Owned by | …이(가) 담당한다 |
| Verified by | …로 검증된다 |
| Defined in | …에 정의되어 있다 |
| Lives in | …에 위치한다 / …에 있다 |
| Reference | 참조 |
| See `path` | `path` 참조 |
| For full context | 전체 맥락은 |
| Drop in to | …에 끼워 넣는다 |
| Wire up | 연결한다 |
| Stub out | stub으로 둔다 |
| End-to-end | end-to-end (첫 등장 시 "end-to-end (전체 흐름)") |
| Out of scope | 본 작업의 범위 밖 |
| Status as of YYYY-MM-DD | YYYY-MM-DD 기준 상태 |
| Last updated | 마지막 갱신 |
| cache (verb, "to cache") | 캐시한다 / 캐시하지 않는다 |
| cache (noun, the cache itself) | 캐시 |
| rephrase as conditional | 조건문 (conditional) 형태로 재서술한다 |

---

## 11. 유지 vs 변환 — 의사결정 트리

문구가 본 용어집에 없을 때 적용한다.

```
이 문구가 …
├── 코드 식별자 / 파일 경로 / API 이름인가?      → 영문 유지
├── 표준 marker인가?                              → 영문 유지 (§7)
├── 약어 (ABP, MAP, EMR …)인가?                  → 영문 유지 (§3)
├── 프레임워크 / 라이브러리 / 모델 이름인가?     → 영문 유지 (§2)
├── ML / 평가 / 통계 용어인가?                    → 영문 유지 (§2)
├── 임상 용어 (질환·약물·해부)인가?              → 한글 + 영문 병기 (§5)
├── 프로젝트 핵심 컨셉 (modality-agnostic 등)? → 영문 유지, 첫 등장 시 한글 풀이 (§6)
├── 표 컬럼 헤더인가?                              → §9 참조
├── 자주 쓰는 메타 표현인가?                      → §10 참조
└── 그 외 일반 설명문                            → 한글로 변환
```

의문이 남으면 **영문 유지** 후 변환 작업 보고 시 사용자에게 질문한다. **추측 변환 금지** (사용자의 변환 원칙 6 "추측 금지").

---

## 12. 적용 우선순위

한글 변환 작업은 다음 순서로 진행된다 (사용자 지시).

1. **Phase 1 — 핵심 5개 sample**: `CLAUDE.md`, `docs/project_brief.md`, `.plans/master_plan.md`, `docs/decisions/ADR-011-mock-fm-strategy.md` (현재 유일한 ADR), `.plans/stage1_preparation/plan_1.1_vitaldb_exploration.md`. → 스타일 fix 후 확정.
2. **Phase 2 — 추가 ADR**: 현재는 ADR-011 단 1개. 8개 design decision 별도 ADR이 미작성 상태이므로 Phase 2는 작성 vs 보류 결정이 먼저 필요(사용자 지시 §14 brief). 한글 변환만 본다면 본 Phase는 ADR-011 외에는 비어 있음.
3. **Phase 3 — 나머지 plan + analysis + findings + placeholder**: 12 plan + 3 analysis + 1 findings + 4 stage placeholder + 4 mock plan(plan_1.{1.5,2.5,6.5,7.5}).
4. **Phase 4 — Cross-reference 재검증**.

> 본 우선순위는 `docs/analysis/step5_plan.md` step 1–6 (terminology → patch → 변환 3 phase → 검증)과 일치한다.

---

## 13. 변경 관리

본 용어집은 살아 있는 문서다.

- 새 용어 등장 → 발견 즉시 본 파일에 추가 + 같은 PR에 변환 적용.
- 표준 표기 변경 → 본 파일을 갱신 + 영향 받는 모든 문서 일괄 패치(같은 commit).
- 모호한 경우 → **영문 유지 + `[TODO: terminology]` marker** 후 사용자 확인.

`MEMORY.md`나 다른 agent memory에는 본 용어집을 *복제하지 않는다*. 본 파일이 유일 SoT다.
