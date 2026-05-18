# Pre-Phase 3 — VitalDB Quick Exploration: 발견 사항 (Findings)

> 2026-05-16 생성. Live VitalDB metadata (`https://api.vitaldb.net/cases`, `/trks`) 기반.
> vitaldb package: 1.6.0. Python 3.13.3.
> Cache: `docs/notebooks/_cache/{cases,trks}.csv`.
> Companion script: `docs/notebooks/00_vitaldb_quick_exploration.py`.

---

## 1. 전체 case 수 (Total cases)

| metric | value |
|--------|-------|
| n_cases | **6,388** |
| n_columns | 74 |
| Brief §4 가정 | 6,388 (비심장 (non-cardiac) 수술) |
| Δ vs brief | **0 — 정확히 일치** ✅ |

`vitaldb.load_clinical_data()`는 0 row 반환 (login 필요로 추정). `https://api.vitaldb.net/cases`의 public CSV endpoint가 운용 경로이며 전체 6,388을 반환한다. **`plan_1.1`은 CSV endpoint를 표준으로 한다. `load_clinical_data`는 사용하지 않는다.**

---

## 2. 수술 유형 분포 (Surgery type distribution)

### `department` — 1차 4-bucket axis

| department | n | pct |
|-----------|---|-----|
| General surgery | 4,930 | 77.2% |
| Thoracic surgery | 1,111 | 17.4% |
| Gynecology | 230 | 3.6% |
| Urology | 117 | 1.8% |

**Verdict (판정)**: VitalDB의 `department` axis가 프로젝트의 `general / thoracic / urologic / gynecologic` taxonomy (project_brief §1 characteristic #1, `plan_1.5_surgery_context.md`)에 **1:1** 매핑된다. 별도 매핑 작업 불필요.

⚠️ **심한 불균형 (severely imbalanced)**: General 77% vs Urology 2%. Stratified split과 stratified 평가가 필수. Urology (n = 117) per-department subgroup 분석은 noisy하다 — 다른 department와 pooling하거나 wide CI (신뢰구간)로 보고할 것.

### `optype` — 더 세밀한 surgical site (top 11)

| optype | n |
|--------|---|
| Colorectal | 1,350 |
| Biliary/Pancreas | 812 |
| Others | 799 |
| Stomach | 676 |
| Major resection | 584 |
| Minor resection | 553 |
| Breast | 434 |
| Transplantation | 403 |
| Vascular | 262 |
| Hepatic | 258 |
| Thyroid | 257 |

### `approach`

| approach | n | pct |
|----------|---|-----|
| Open | 3,365 | 52.7% |
| Videoscopic | 2,754 | 43.1% |
| Robotic | 269 | 4.2% |

### `opname`

- Unique 수술 procedure: **241**
- Top 10: Cholecystectomy (503), Distal gastrectomy (342), Lung lobectomy (332), Breast-conserving surgery (295), Anterior resection (247), Lung wedge resection (236), Excision (228), Exploratory laparotomy (215), Hemicolectomy (193), Low anterior resection (181).

---

## 3. 인구 통계 (Demographics)

| field | n | missing | mean ± std | p5 / p50 / p95 | min / max |
|-------|---|---------|------------|----------------|-----------|
| age | 6,388 | 0 | 57.3 ± 15.0 | 30 / 59 / 78 | **0.3 / 94** |
| weight (kg) | 6,388 | 0 | 61.5 ± 12.0 | 44.5 / 60.5 / 81.8 | 4.8 / 139.7 |
| height (cm) | 6,388 | 0 | 162.2 ± 9.9 | 148.3 / 162.2 / 176.9 | 42.0 / 188.6 |
| BMI | 6,388 | 0 | 23.3 ± 3.6 | 17.8 / 23.1 / 29.6 | 11.3 / 43.2 |
| ASA | 6,255 | 133 | 1.85 ± 0.66 | 1 / 2 / 3 | 1 / **6** |

### `sex`

| sex | n |
|-----|---|
| M | 3,243 (50.8%) |
| F | 3,145 (49.2%) |

### ⚠️ 이상치 (Anomalies to flag)

- **Pediatric inclusion**: min age = 0.3세, min weight 4.8 kg, min height 42 cm. brief는 "성인"이라고 명시하지 않는다. 성인 (≥ 18세)로 제한하거나 pediatric case를 포함할지 **결정 필요**.
- **ASA max = 6**: ASA 6 = 뇌사 장기 기증자 (brain-dead organ donor). Transplantation case일 가능성. 포함을 유지하되 확인할 가치 있음.
- ASA missing 133 case (2.1%) — 수용 가능.
- 그 외 demographic field는 모두 **missing 0** — 깨끗하다.

---

## 4. 수술 시간 (Surgery duration)

`opend − opstart`로 계산, 단위는 분.

| stat | value |
|------|-------|
| n with duration | 6,388 (missing 0) |
| mean ± std | 136.0 ± 101.2 min |
| p5 / p25 / p50 / p75 / p95 | 25 / 60 / 110 / 190 / 325 min |
| min / max | 1.4 / **955.0** min |
| negative / zero | 0 / 0 |

### Duration bin

| bin | n | pct |
|-----|---|-----|
| < 30 min | **442** | 6.9% |
| 30–60 min | 1,123 | 17.6% |
| 60–120 min | 1,825 | 28.6% |
| 120–240 min | 2,050 | 32.1% |
| ≥ 240 min | 948 | 14.8% |

### 코호트 exclusion 영향 (rule: `op_duration < 30 min` drop)

- **442 case** 제외.
- 남는 코호트: **6,388 − 442 = 5,946 case**.
- ✅ brief §4.1의 예상 윈도우 5,800–6,000 안에 들어온다.

### Department별 (median + p95 + < 30 min count)

| department | n | median (min) | p95 (min) | < 30 min |
|-----------|---|--------------|-----------|----------|
| General surgery | 4,930 | 110 | 330 | 354 |
| Thoracic surgery | 1,111 | 113 | 319 | 56 |
| Urology | 117 | 145 | 273 | **23 (19.7%)** |
| Gynecology | 230 | 95 | 253 | 9 |

⚠️ **Urology는 19.7%가 30분 미만**이다. `< 30 min` 필터 후 Urology 코호트는 약 94 case로 줄어든다. Subgroup 통계가 noisy하다.

---

## 5. Modality 가용성 (Modality availability)

| dataset stat | value |
|--------------|-------|
| 최소 1개 track 보유 case | 6,388 (100%) |
| unique track name | **196** |
| 전체 (caseid, tname) pair | 486,449 |

### Priority track 가용성 (전체 6,388 case 기준 %)

| track (project_brief §4 priority) | n | pct | verdict |
|----------------------------------|---|-----|---------|
| `SNUADC/ART` (invasive ABP wave) | 3,645 | 57.1% | match |
| `SNUADC/PLETH` (PPG) | 6,157 | 96.4% | match |
| `SNUADC/ECG_II` | 6,355 | 99.5% | match |
| `Solar8000/ART_MBP` | 3,724 | 58.3% | match |
| `Solar8000/NIBP_MBP` | 5,763 | 90.2% | match |
| `BIS/EEG1_WAV` | 5,871 | 91.9% | match |
| **`Primus/SEVOFLURANE_VOL`** | **0** | **0.0%** | ⚠️ **track name 오류** |
| `Orchestra/PPF20_CE` | 3,511 | 55.0% | match |

### ⚠️ Track-name 정정

Priority list는 `Primus/SEVOFLURANE_VOL`이 존재한다고 가정한다. **존재하지 않는다.** 실제 sevoflurane track은 다음 두 개다.

| actual track | n | pct |
|--------------|---|-----|
| `Primus/EXP_SEVO` | 3,687 | 57.7% |
| `Primus/INSP_SEVO` | 3,687 | 57.7% |

→ `project_brief.md §4`와 `plan_1.1` priority list가 patch되어야 한다.

### 파생 가용성 (핵심 narrative)

| modality | % cases |
|----------|---------|
| ABP invasive (`SNUADC/ART`) | 57.1% |
| ABP numeric (`Solar8000/ART_MBP`) | 58.3% |
| **ABP any (ART or ART_MBP)** | **58.3%** |
| **ABP absent** | **41.7% (2,663 case)** |
| PPG (`SNUADC/PLETH`) | 96.4% |
| ECG II (`SNUADC/ECG_II`) | 99.5% |
| NIBP (`Solar8000/NIBP_MBP`) | 90.2% |
| BIS EEG | 91.9% |
| Propofol Ce | 55.0% |
| Triplet (ECG II + PLETH + ABP-any) | 54.9% |

### Department별 ABP-absent

| department | abp_absent pct |
|-----------|-----|
| Thoracic surgery | **2.5%** |
| Gynecology | 18.3% |
| Urology | 29.1% |
| General surgery | **51.9%** |

→ **핵심 설계 관찰**: ABP 가용성은 department와 **강하게 상관**한다. Thoracic 수술은 거의 항상 invasive ABP가 있고, General 수술은 절반 정도만 있다. modality-agnostic 주장은 반드시 **department별 stratified ABP-absent rate**로 보고해야 하며, 전체 41.7% 단일 수치로 보고하면 안 된다.

### Brief가 빠뜨린 modality: EV1000

`EV1000/ART_MBP`는 **592 case** (9.3%)에 존재하며, project_brief priority list에 없는 세 번째 ABP source다. `plan_1.1`은 이를 `abp_any`에 병합할지 별도로 보고할지 결정해야 한다. `Solar8000/FEM_MBP`도 142 case (femoral artery line)에 존재한다.

### 보너스 발견 — 약물 track 분포

- **Remifentanil RFTN20**이 **4,773 case (74.7%)**에 존재 — *Propofol보다 더 보편적이다.*
- Propofol PPF20: 3,512 case (55.0%).
- 16-tool suite는 Propofol Ce를 "anesthesia drugs"에 배치한다. 단일 대표 anesthetic-effect-site 신호로는 **Remifentanil이 더 가용한 채널**이다. `plan_1.3` (EMR tool)과 `plan_1.1` priority list가 이를 반영하면 좋다.

---

## 6. 설계 가정 vs 실측 (Design assumption vs reality)

| 가정 (project_brief / master_plan) | 관측 | 판정 |
|-----------------------------------|------|------|
| 6,388 case (비심장 수술, SNUH, 2016년 8월 – 2017년 6월) | 6,388 | ✅ **정확히 일치** |
| 4-category 수술 taxonomy (general / thoracic / urologic / gynecologic) | `department` field에 정확히 그 4개 | ✅ **정확히 일치** |
| 코호트 exclusion 수술 < 30 min | 442 case | ✅ 작고 합리적 |
| 예상 최종 코호트 5,800–6,000 | 6,388 − 442 = **5,946** | ✅ **밴드 안** |
| modality-agnostic 주장은 ABP-absent fraction이 자명하지 않아야 함 | 41.7% (전체) | ✅ **매우 강한 근거** |
| Priority modality `Primus/SEVOFLURANE_VOL` | 0 case | ❌ **잘못된 track name** — `Primus/EXP_SEVO` / `INSP_SEVO` 사용 |
| 12 waveform modality | 196 unique track 전체 | partial — `plan_1.1`의 전수 enumeration 필요 |
| 대부분 case에 PPG / ECG / ABP triplet 존재 | triplet 54.9%, ECG II 99.5%, PPG 96.4% | ✅ ECG + PPG는 거의 universal. triplet ≈ ABP 가용성. |

---

## 7. 놀라운 발견 / 짚어둘 사항 (Surprises / things worth raising)

1. **ABP 부재가 department-dependent** (Thoracic 2.5% vs General 51.9%). Stratification 없이 modality-agnostic story를 논하면 오해 소지. → paper outline에 flag.
2. **Pediatric case 존재** (min age 0.3세). brief는 age 컷오프에 침묵. → 명시적 결정 필요 (성인 only vs 전 연령). `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`.
3. **Sevoflurane track name 오류** — `project_brief.md §4` priority list. → patch.
4. **Remifentanil이 Propofol보다 가용성 높음** (effect-site 신호로서). → `plan_1.3` (`query_anesthesia_drugs`)에 primary anesthesia channel로 추가 가능.
5. **`load_clinical_data()`가 0 row 반환** — package 내 helper는 login 필요로 추정. CSV endpoint가 운용 경로. → `plan_1.1` API reference task에 문서화.
6. **ASA max = 6**은 donor-organ transplantation case 가능성. 포함 의도 확인.
7. **Urology subgroup (n = 117 → ~94 post-filter)**은 안정된 subgroup metric을 위해 너무 작다. → 다른 department와 pool하거나 wide CI로 보고.
8. **241개 unique `opname`** — 4-bucket `department` taxonomy로 충분히 collapse됨. 더 세밀한 분석이 필요할 때 `optype` axis (11 main type)가 유용한 중간 granularity.

---

## 8. Phase 3 진입 전 필요한 변경 (Required changes proposed)

본 finding은 agent charter 설계를 무효화하지 않는다. 다만 작은 upstream patch가 필요하다.

### `docs/project_brief.md` — patch

| § | change |
|---|--------|
| §4 priority list | `Primus/SEVOFLURANE_VOL` → `Primus/EXP_SEVO`로 교체 (`INSP_SEVO`는 대안으로 표기) |
| §4 priority list (선택 추가) | `EV1000/ART_MBP`와 `Solar8000/FEM_MBP`를 ABP family note에 추가 |
| §4.1 cohort policy | `plan_1.2` 시작 전 pediatric inclusion에 대한 **명시적 결정** (성인 only vs 전 연령) |
| §4.1 cohort policy | 실제 `< 30 min` 필터가 442 case → 5,946 case로 줄임을 명시 (이전 "5,800–6,000 예상"에서 정확값으로) |
| §6.3 / §7.1 priority modality (`docs/project_brief.md` "modality-agnostic" 주장) | 한 줄 caveat 추가: "ABP-absent fraction은 department별로 다르다 (Thoracic 2.5% vs General 51.9%). 평가는 반드시 stratify할 것" |

### `.plans/master_plan.md` — patch

| § | change |
|---|--------|
| §8 Risk Register | 행 추가: "Severe department imbalance (Urology n ≈ 94 post-filter)" → 담당 clinical-evaluator → 대응책: pooling 또는 wide CI 보고 |
| §8 Risk Register | 행 추가: "ABP-absent rate가 department-correlated. 일관 modality-agnostic story를 위협" → 담당 project-planner |

### `.plans/stage1_preparation/plan_1.1_vitaldb_exploration.md` — patch

- API reference task에서 `vitaldb.load_clinical_data()`를 `pandas.read_csv("https://api.vitaldb.net/cases")`로 교체
- Subtask 추가: **196 unique track** 전수 enumeration (`trks.csv` 카탈로그화)
- Subtask 추가: department별 stratified modality 가용성 표 산출 (Thoracic vs General 등)

### `.plans/stage1_preparation/plan_1.2_cohort_definition.md` — patch

- Manifest write 전 **pediatric inclusion 결정**을 `[CLINICIAN-REVIEW]` blocker로 노출
- **ASA = 6 inclusion 결정** (donor organ case) 동일하게 노출

### `.plans/stage1_preparation/plan_1.5_surgery_context.md` — patch

- "Surgery type taxonomy 정의" task를 "**기존 `department` 4-bucket을 taxonomy로 confirm**"으로 교체 (이미 맞음 — design 작업 불필요)
- 필요 시 mid-granularity 옵션으로 `optype` (11 bucket) 노트 추가

### `.plans/stage1_preparation/plan_1.3_emr_tools.md` — patch

- `query_anesthesia_drugs`에 Remifentanil (`Orchestra/RFTN20_*`)을 first-class channel로 추가 (Propofol만이 아니라). Remi가 더 가용 (74.7% vs 55.0%).

### Phase 3 (agent charter) 영향

- `vitaldb-domain-expert` charter: **CSV endpoint** (`load_clinical_data` X)가 운용 경로임을 charter에 박는다. `department`가 정식 surgery axis임을 명시. **Track name은 반드시 `trks.csv`에서 lookup하며 추정하지 않는다**.
- `clinical-evaluator` charter: standing review question에 department imbalance + Pediatric / ASA-6 inclusion 포함.
- 새 agent 불필요. 기존 책임 제거도 불필요.

---

## 9. 핵심 결론 (Bottom line)

**Brief는 압도적으로 옳다.** 점검한 7개 가정 중 **6개는 정확히 확인된다** (case 수, taxonomy, 코호트 정책 결과, modality-agnostic 전제 타당성, ECG / PPG 보편성, 예상 post-filter 코호트 크기). 명백한 오류는 single track name (`Primus/SEVOFLURANE_VOL` → `EXP_SEVO`)뿐이다. 세 가지 soft issue (pediatric inclusion, ASA = 6 inclusion, department-correlated ABP availability)는 명확화 사항이지 재설계 사항이 아니다.

**권고 (Recommendation)**: 위 6개 patch section을 brief + master_plan + `plan_1.{1, 2, 3, 5}`에 적용한 후 Phase 3 (agent charter)에 변경 없이 진입한다.

---

## 10. 재현성 (Reproducibility)

```powershell
# from C:\Projects\VitalAgent
.\.venv\Scripts\python.exe notebooks\00_vitaldb_quick_exploration.py
# Cache files: notebooks\_cache\{cases,trks}.csv  (delete to force re-fetch)
```

Analysis 1–3은 inline `python -c` 명령으로도 실행되었다. 본 세션의 tool output에서 raw JSON을 확인할 수 있다.
