# PUMP / Drug — Design Feasibility 탐색 (pre plan_1.1)

> 2026-05-17. Cache snapshot 2026-05-16 (`docs/notebooks/_cache/{cases,trks}.csv`).
> Companion script: `docs/notebooks/01_pump_drug_exploration.py`.
> 본 문서는 plan_1.1 본격 작업이 아닌 **OpSight intervention-response 자동화 feasibility** 사전 탐색 산출물이다.

## 0. 한 줄 요약 (TL;DR)

- `PUMP*` 또는 `DRUG*` 패턴 채널은 VitalDB schema 에 **존재하지 않는다**. 모든 drug infusion 기록은 **`Orchestra/<DRUG>_<VAR>`** 형식이다.
- Vasopressor / inotrope **infusion** (Orchestra) 의 case-level 가용률은 모두 **5% 미만** (PHEN 2.0% · NEPI 1.4% · DOPA 0.5% · EPI 0.1%).
- 반면 **bolus** 형태 vasopressor 는 `cases.csv` 의 `intraop_eph` (50.3% case 에서 > 0), `intraop_phe` (13.2%), `intraop_epi` (1.4%) 에 기록되며 **per-event timestamp 가 없다**.
- Fluid / transfusion (`intraop_crystalloid` 93.6%, `intraop_rbc` 5.5%, `intraop_ffp` 2.0%) 도 **case-level 누적값만** 있어 real-time stream 감지 불가.
- **결론**: Tool 9 (vasoactive query) 는 Orchestra/* schema 로 정의 가능하지만 가용 cohort 가 작다. Tool 10 (fluid/blood) 은 fully automatic 불가 → **mixed-initiative** (clinician annotation) 또는 case-end retrospective 만 가능. Paper narrative 도 mixed-initiative 로 framing 권장.

## 1. Schema reality check

- `tname.str.contains('PUMP')` → **0 hit** (즉 0)
- `tname.str.contains('DRUG')` → **0 hit** (즉 0)
- `Orchestra/*` prefix unique track 수: **51**

user 의 가설 'PUMP_CE 등 PUMP 채널 존재' 는 schema 와 어긋난다. 실제로는 drug-specific code-prefix (예: `Orchestra/PPF20_CE`, `Orchestra/PHEN_RATE`) 가 존재한다. user 가 '`PUMP*`' 로 호명한 것은 `Orchestra/*` 와 등가로 해석한다.

## 2. Drug class taxonomy (Orchestra/*)

> 본 분류는 모두 **[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]** 잠정안이다.

### 2.1 Class 별 case 수 (drug 1 개 이상 보유 case)

| class | n_cases (≥1 drug 보유) | % cohort |
|-------|-----------------------:|---------:|
| opioid | 4,841 | 75.78% |
| hypnotic | 3,512 | 54.98% |
| paralytic | 282 | 4.41% |
| vasopressor | 210 | 3.29% |
| vasodilator | 123 | 1.93% |
| other | 97 | 1.52% |
| inotrope | 45 | 0.70% |
| sedative | 10 | 0.16% |
| antiarrhythmic | 3 | 0.05% |

### 2.2 Drug 별 (drug_code 단위 unique caseid)

| drug_code | drug_name | class (잠정) | n_cases | % cohort |
|-----------|-----------|-------------|--------:|---------:|
| RFTN20 | remifentanil 20μg/mL | opioid | 4,773 | 74.72% |
| PPF20 | propofol 20mg/mL | hypnotic | 3,512 | 54.98% |
| ROC | rocuronium | paralytic | 281 | 4.40% |
| PHEN | phenylephrine | vasopressor | 127 | 1.99% |
| FUT | futhan / nafamostat (protease inh) | other | 94 | 1.47% |
| PGE1 | prostaglandin E1 (pulmonary) | vasodilator | 90 | 1.41% |
| NEPI | norepinephrine | vasopressor | 88 | 1.38% |
| RFTN50 | remifentanil 50μg/mL | opioid | 68 | 1.06% |
| DOPA | dopamine | inotrope | 33 | 0.52% |
| NTG | nitroglycerin | vasodilator | 32 | 0.50% |
| EPI | epinephrine | inotrope | 9 | 0.14% |
| DEX2 | dexmedetomidine (2) | sedative | 6 | 0.09% |
| MRN | milrinone | inotrope | 5 | 0.08% |
| DEX4 | dexmedetomidine (4) | sedative | 4 | 0.06% |
| DOBU | dobutamine | inotrope | 3 | 0.05% |
| OXY | oxytocin (uterotonic) | other | 3 | 0.05% |
| DTZ | diltiazem | antiarrhythmic | 2 | 0.03% |
| AMD | amiodarone | antiarrhythmic | 1 | 0.02% |
| NPS | nitroprusside | vasodilator | 1 | 0.02% |
| VASO | vasopressin | vasopressor | 1 | 0.02% |
| VEC | vecuronium | paralytic | 1 | 0.02% |

## 3. Vasoactive infusion (Orchestra/*) × department

| drug | General surgery (n=4930) | Thoracic surgery (n=1111) | Gynecology (n=230) | Urology (n=117) | total |
|---|---|---|---|---|---|
| PHEN | 68 (1.4%) | 48 (4.3%) | 9 (3.9%) | 2 (1.7%) | 127 |
| NEPI | 75 (1.5%) | 13 (1.2%) | 0 (0.0%) | 0 (0.0%) | 88 |
| DOPA | 33 (0.7%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 33 |
| EPI | 8 (0.2%) | 1 (0.1%) | 0 (0.0%) | 0 (0.0%) | 9 |
| DOBU | 0 (0.0%) | 3 (0.3%) | 0 (0.0%) | 0 (0.0%) | 3 |
| VASO | 1 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 1 |
| NTG | 20 (0.4%) | 10 (0.9%) | 1 (0.4%) | 1 (0.8%) | 32 |

핵심 관측:
- **PHEN** (phenylephrine infusion) 이 가장 흔하지만 그래도 4.3% (Thoracic) 가 최대.
- **NEPI** (norepinephrine) 은 General + Thoracic 에만 존재. Gynecology / Urology 0 case.
- **DOPA / EPI / DOBU / VASO** 는 총합 < 50 case — 단독 학습 불가, family-level pooling 필요.

## 4. `cases.csv` `intraop_*` field 가용성 (case-level 누적값)

**핵심 한계**: 본 field 는 case 종료 시점의 **누적 합계**일 뿐 per-event timestamp 가 없다. 시뮬레이션 시점 t 에서 'phenylephrine 50μg 방금 투여' 같은 detection 은 불가능하다.

| field | n_nonnull | % | n_>0 | %_>0 | mean | p50 | p95 | max |
|-------|----------:|--:|-----:|-----:|-----:|----:|----:|----:|
| `intraop_ca` | 6,388 | 100.0% | 868 | 13.6% | 120.782 | 0.0 | 600.0 | 15900.0 |
| `intraop_colloid` | 6,388 | 100.0% | 531 | 8.3% | 32.114 | 0.0 | 300.0 | 1900.0 |
| `intraop_crystalloid` | 5,980 | 93.6% | 5,980 | 93.6% | 1060.237 | 700.0 | 3200.0 | 23800.0 |
| `intraop_ebl` | 3,987 | 62.4% | 3,976 | 62.2% | 363.211 | 150.0 | 1100.0 | 30100.0 |
| `intraop_eph` | 6,388 | 100.0% | 3,211 | 50.3% | 7.754 | 5.0 | 30.0 | 300.0 |
| `intraop_epi` | 6,388 | 100.0% | 89 | 1.4% | 7.895 | 0.0 | 0.0 | 37220.0 |
| `intraop_ffp` | 6,388 | 100.0% | 129 | 2.0% | 0.129 | 0.0 | 0.0 | 52.0 |
| `intraop_ftn` | 6,388 | 100.0% | 1,168 | 18.3% | 17.044 | 0.0 | 100.0 | 200.0 |
| `intraop_mdz` | 6,388 | 100.0% | 80 | 1.2% | 0.037 | 0.0 | 0.0 | 8.0 |
| `intraop_phe` | 6,388 | 100.0% | 844 | 13.2% | 32.631 | 0.0 | 180.0 | 4100.0 |
| `intraop_ppf` | 6,388 | 100.0% | 2,335 | 36.5% | 39.777 | 0.0 | 150.0 | 200.0 |
| `intraop_rbc` | 6,388 | 100.0% | 352 | 5.5% | 0.47 | 0.0 | 1.0 | 800.0 |
| `intraop_rocu` | 6,388 | 100.0% | 5,942 | 93.0% | 72.825 | 70.0 | 130.0 | 330.0 |
| `intraop_uo` | 3,707 | 58.0% | 3,684 | 57.7% | 250.867 | 160.0 | 740.0 | 5750.0 |
| `intraop_vecu` | 6,388 | 100.0% | 12 | 0.2% | 0.017 | 0.0 | 0.0 | 20.0 |

### 4.1 주요 vasopressor / fluid bolus × department

**`intraop_eph`**

| department | n_>0 / n_total | %_>0 | mean (when >0) |
|-----------|---------------:|-----:|---------------:|
| General surgery | 2652/4930 | 53.8% | 16.11 |
| Thoracic surgery | 380/1111 | 34.2% | 11.46 |
| Gynecology | 113/230 | 49.1% | 14.29 |
| Urology | 66/117 | 56.4% | 12.50 |

**`intraop_phe`**

| department | n_>0 / n_total | %_>0 | mean (when >0) |
|-----------|---------------:|-----:|---------------:|
| General surgery | 619/4930 | 12.6% | 243.33 |
| Thoracic surgery | 172/1111 | 15.5% | 251.94 |
| Gynecology | 42/230 | 18.3% | 302.62 |
| Urology | 11/117 | 9.4% | 161.82 |

**`intraop_epi`**

| department | n_>0 / n_total | %_>0 | mean (when >0) |
|-----------|---------------:|-----:|---------------:|
| General surgery | 85/4930 | 1.7% | 590.48 |
| Thoracic surgery | 3/1111 | 0.3% | 76.67 |
| Gynecology | 1/230 | 0.4% | 10.00 |
| Urology | 0/117 | 0.0% | 0.00 |

**`intraop_rbc`**

| department | n_>0 / n_total | %_>0 | mean (when >0) |
|-----------|---------------:|-----:|---------------:|
| General surgery | 307/4930 | 6.2% | 8.02 |
| Thoracic surgery | 35/1111 | 3.1% | 3.49 |
| Gynecology | 8/230 | 3.5% | 51.88 |
| Urology | 2/117 | 1.7% | 2.50 |

**`intraop_ffp`**

| department | n_>0 / n_total | %_>0 | mean (when >0) |
|-----------|---------------:|-----:|---------------:|
| General surgery | 117/4930 | 2.4% | 6.54 |
| Thoracic surgery | 12/1111 | 1.1% | 4.83 |
| Gynecology | 0/230 | 0.0% | 0.00 |
| Urology | 0/117 | 0.0% | 0.00 |

**해석 (잠정 [CLINICIAN-REVIEW])**:
- **`intraop_eph` 50.3% case** — ephedrine 은 SNUH 비심장 술중 가장 흔한 IV bolus vasopressor 로 추정된다. 그러나 Orchestra/* 채널에 ephedrine 이 없으므로 syringe pump 가 아닌 **IV push (직접 정주)** 로 투여된 것으로 추정된다 [CLINICIAN-REVIEW].
- **`intraop_phe` 13.2% case** + **Orchestra/PHEN 2.0% case** — phenylephrine 은 일부 case 에서 syringe pump (Orchestra) 로, 다수 case 에서 IV bolus (intraop_phe) 로 투여된 것으로 보인다.
- **`intraop_rbc` 5.5%**, **`intraop_ffp` 2.0%** — transfusion 은 sparse 하지만 비심장 major surgery 의 outcome label 로는 의미 있는 수준.

## 5. Bolus vs continuous 식별 trial (Orchestra/PHEN, n=3 case)

> 식별 규칙 (잠정): rate_>0 segment dur < 60s ⇒ bolus-like; >= 600s ⇒ continuous infusion (잠정, [CLINICIAN-REVIEW] 필요)

| caseid | duration_s | n_segments | short (<60s) | medium (60–600s) | long (≥600s) |
|-------:|-----------:|-----------:|-------------:|-----------------:|-------------:|
| 20 | 25,875 | 94 | 70 | 1 | 23 |
| 28 | 26,520 | 84 | 64 | 0 | 20 |
| 61 | 8,690 | 16 | 12 | 1 | 3 |

- case 20: first 8 events = (187, 823, 636s), (824, 1812, 988s), (1813, 1821, 8s), (1822, 1825, 3s), (1826, 1828, 2s), (1829, 1830, 1s), (1831, 1832, 1s), (1833, 1836, 3s); rate_max = 10.20
- case 28: first 8 events = (6732, 7402, 670s), (7403, 7410, 7s), (7411, 7412, 1s), (7413, 8399, 986s), (8400, 8409, 9s), (8410, 8417, 7s), (8418, 8419, 1s), (8420, 9418, 998s); rate_max = 20.00
- case 61: first 8 events = (4773, 5577, 804s), (5578, 5579, 1s), (5580, 5581, 1s), (5582, 5583, 1s), (5584, 5589, 5s), (5590, 6613, 1023s), (6614, 6615, 1s), (6616, 6619, 3s); rate_max = 20.00

**관측**:
- 한 case 안에서도 short bolus 와 long continuous infusion 이 **섞여** 나타난다 → 단일 case 가 'bolus-only' 또는 'infusion-only' 로 분류되지 않는다.
- 매우 짧은 sub-second segment 가 다량 발생하는 경우는 syringe pump 의 quick-toggle (e.g., 정밀 dose 조정) 일 수 있어 noise filter 필요 [CLINICIAN-REVIEW].
- **결론**: rate-segmentation 기반 자동 detection 은 가능하나 single-rule 로 'bolus' label 을 신뢰성 있게 부여하기는 어렵다.

## 6. Agent design 영향 분석

### 6.1 Tool 9 (`query_vasoactive_drugs`) — I/O 정의 가능 여부

**가능**. Orchestra/* schema 가 명확하므로 다음과 같이 정의 가능:

```
Input:
  caseid: int
  simulated_now: float    # seconds since case start, end-exclusive
  window_s: float = 30.0  # look-back window

Output (list[dict]):
  drug_code: str   # 'PHEN' | 'NEPI' | 'DOPA' | 'EPI' | 'DOBU' | 'VASO' | 'NTG' | ...
  class: str       # 'vasopressor' | 'inotrope' | 'vasodilator' (CLINICIAN-REVIEW 잠정)
  infusion_rate_mL_per_h: float
  effect_site_conc: float | None    # CE 가 존재할 때만 (PHEN 등 일부에는 없음)
  cumulative_volume_mL: float
  source: 'Orchestra/<DRUG>_RATE'
```

**제약**:
- 가용 cohort 가 매우 작다 (sum of PHEN+NEPI+DOPA+EPI+DOBU+VASO+NTG ≈ 380 cases, 6%).
- **Ephedrine bolus (50% case) 는 본 tool 로 캡쳐 불가** — Orchestra 채널에 없음.
- Bolus 자동 식별은 가능하지만 [CLINICIAN-REVIEW] 필요한 잠정 rule.

### 6.2 Tool 10 (`query_fluid_blood`) — feasibility

**Real-time stream 으로는 fully automatic 불가**. 이유:
- `cases.csv` `intraop_crystalloid / colloid / rbc / ffp / ebl / uo` 는 **case-level 누적값**.
- per-event timestamp 가 없어 'simulated_now=t 시점 직전 fluid bolus' 를 query 할 수 없다.

**가능한 design 대안**:
- (a) `tool_10_retrospective`: caseend 시점에만 누적 fluid 출력 — outcome evaluation 용도로만 사용
- (b) `tool_10_annotation_driven`: clinician 사용자가 '방금 RBC 1u 주입했음' 같은 manual annotation 을 stream 으로 제공 → mixed-initiative
- (c) `tool_10_physiological_inference`: ABP/CVP/HR 의 step-change 로 fluid bolus 의 *effect* 를 추정 — 단 이는 **fluid 투여 자체의 detection 이 아니고 fluid response 의 추정** 이며 confounder 다대다 [CLINICIAN-REVIEW]

→ **권장**: (a) + (b) 조합. paper 에서 'fluid/blood is evaluated retrospectively (case-level) and via optional clinician annotation' 로 framing.

### 6.3 Intervention response head 학습 데이터 추정

| event type | source | n_cases | estimated events |
|-----------|--------|--------:|-----------------:|
| Vasopressor infusion start/stop (Orchestra) | PHEN+NEPI+DOPA+EPI+DOBU+VASO | ≈ 250 | ≈ 1,000 (case 당 ~4 event) |
| Anesthetic infusion change (Orchestra) | PPF20 + RFTN20 | ≈ 5,200 | ≈ 10,000+ |
| Phenylephrine bolus (case-level) | intraop_phe | 844 | n/a (no timestamp) |
| Ephedrine bolus (case-level) | intraop_eph | 3,211 | n/a (no timestamp) |
| Transfusion (case-level) | intraop_rbc + ffp | 481 | n/a (no timestamp) |

→ **자동 감지 가능 event 수**: vasoactive ~1,000 + anesthetic ~10,000 ≈ **11,000 stream events** (Orchestra 만)
→ **case-level only event 수**: ephedrine 3,211 + phenylephrine 844 + transfusion 481 + fluid 5,980 → outcome evaluation 용 retrospective label 로 매우 풍부

### 6.4 Paper narrative — fully automatic vs mixed-initiative

**권장**: **mixed-initiative** framing.

이유:
- Orchestra/* vasoactive infusion 변경은 자동 감지 가능하지만 cohort 의 ~5% 만 cover.
- 가장 흔한 vasopressor intervention (ephedrine 50%, phenylephrine bolus 13%) 는 IV push 라 timestamp 부재 → automatic 불가.
- Fluid / transfusion 도 동일하게 case-level summary 만 존재.

**제안 표현 (영문, paper draft 용)**:
> *OpSight automatically detects continuous vasoactive infusion changes from the syringe-pump record (Orchestra channel; ~5% of cohort). For interventions logged only at the case-level (IV bolus vasopressors, fluid administration, transfusion), OpSight supports clinician annotation during the simulated real-time loop and retrospective evaluation against case-level ground truth.*

## 7. `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` 항목

- (a) Drug code → 임상 class 매핑 (특히 PHEN=vasopressor, DOPA=inotrope vs vasopressor 등 dose-dependent 약물)
- (b) Ephedrine 이 Orchestra/* 에 없는 것이 SNUH practice 에서 일반적 IV push 패턴이라는 가정
- (c) Bolus vs continuous 식별 rule (rate>0 segment < 60s ⇒ bolus) 의 임상적 타당성
- (d) `intraop_*` 누적값을 시간 균등 분배하는 가정의 위험성 (실제 투여 timing 정보 손실)
- (e) Fluid/blood 의 physiological-inference 기반 detection (ABP/CVP step change) 의 confounder
- (f) vasopressor family pooling 시 임상적으로 equivalent dose 정의 (norepi 1μg ≈ phenylephrine ?μg ≈ ephedrine ?mg)

## 8. 4가지 핵심 질문에 대한 답

**(a) Tool 9 (`query_vasoactive_drugs`) 정확한 input/output 정의 가능?**
→ **가능**. 위 §6.1 schema 확정. 단 가용 cohort 가 5% 수준.

**(b) Tool 10 (`query_fluid_blood`) 구현 feasibility?**
→ **부분적**. real-time stream 자동 감지 불가. retrospective (case-end) + optional clinician annotation 으로 scope 축소 권장.

**(c) Intervention response head 학습 데이터 양 대략?**
→ **automatic stream events: ~11,000** (vasoactive 1,000 + anesthetic 10,000). retrospective case-level labels: ephedrine 3,211 + phenylephrine 844 + transfusion 481 + fluid 5,980.

**(d) Paper narrative: fully automatic vs mixed-initiative?**
→ **mixed-initiative**. Vasoactive infusion 은 automatic, IV bolus vasopressor / fluid / transfusion 은 annotation + retrospective.

## 9. ADR 후보 / 회의 안건

1. **ADR-XXX (Tool 10 scope 축소)**: `query_fluid_blood` 를 real-time stream tool 에서 **case-end retrospective + optional clinician annotation tool** 로 재정의. 영향: brief §7 tool suite, plan_1.7 tool spec.
2. **ADR-XXX (Intervention head v1 scope)**: stage 2 intervention response head 의 v1 은 **vasoactive + anesthetic infusion only**. IV bolus / fluid / transfusion 은 v2 (annotation-aware) 로 이연.
3. **회의 안건 (이형철 교수님 그룹)**: 위 §7 의 (a)–(f) 항목 일괄 검토 1 회 — drug class 매핑 확정이 다른 결정의 prerequisite.
4. **brief 수정 후보**: §1 characteristic 의 'fully automatic intervention monitoring' 표현을 'mixed-initiative intervention monitoring' 로 변경 검토.

## 10. 재현성 (Reproducibility)

```bash
.venv/Scripts/python.exe docs/notebooks/01_pump_drug_exploration.py
# Reads: docs/notebooks/_cache/{cases,trks}.csv
# Writes: docs/findings/pump_drug_findings.md
#         docs/notebooks/_cache/{sample100.csv, 01_report.json}
# vitaldb API: only 3 case (PHEN-having) 로드 (Step A6) — ~30 초
```

Seed: `np.random.default_rng(20260517)`. Sample manifest: `_cache/sample100.csv`.

