# Real VitalDB Case Run — Findings (Sprint 5, 2026-05-18)

> 본 문서는 `scripts/run_real_case.py` 작성 + case 1 sample run 진행 시 발견한 *prototype 의 실제 한계*. Mock data 만으로 testing 했을 때는 *보이지 않던* 문제들이 real VitalDB 데이터를 만나며 드러났다.
> 작성 시점: 2026-05-18, Sprint 5.
> 산출물: `data/runs/case1_*.jsonl` + `data/runs/case1_*.summary.json`.

---

## Sample run 결과 — 작동은 OK

| 항목 | 값 |
|------|----|
| Case | VitalDB case_id=1 (general surgery, age=77, op 145분, ABP invasive ✅) |
| Tracks loaded | Solar8000/HR, ART_MBP, NIBP_MBP, PLETH_SPO2, ETCO2, BT + BIS/BIS (7 modality) |
| Sampling | `interval=1.0s` → effective 1 Hz |
| Ticks | 30 × 60초 sim advance = 30 min sim |
| Wall clock | 108 ms (mock FM, real signal) |
| Deep briefs fired | **5 회** (모두 `periodic_check_every_300s` trigger) |
| Hypotension trigger | **0 회** (실제 case 에는 4500s, 5400s 에 진짜 hypotension 존재 — 30 min 범위 밖) |
| 9-section brief | ✅ 모두 채워짐 + `[CLINICIAN-REVIEW]` marker 보존 |

→ **End-to-end 작동**. 진짜 VitalDB ABP/HR/SpO2/BIS 로 brief 생성됨. 한글 출력 + leakage 0 + trace JSONL 저장 모두 정상.

---

## Findings — 8 issue (priority 정렬)

### 🔴 Issue 1: Sensor artifacts (MAP −9 mmHg, 344 mmHg) — *mock data 에 없던 문제*

**관찰**: case 1 의 raw ABP statistics:
```
mean = 82.2, std = 42.7, min = -9.0, max = 344.0
```
- MAP min −9 mmHg = transducer zero (line 연결 안됨 상태)
- MAP max 344 mmHg = line flush / 충격 / NIBP cuff 부풀림
- std 42.7 (정상 ~5–10 의 4배) — artifact 가 dominate

**영향**:
- Tool 18 `describe_signal` 의 mean/std 가 *임상적으로 무의미*
- Tool 1 `predict_hypotension` 의 MAP score 계산이 artifact 포함 mean 기준 → 잘못된 risk
- Tool 20 `compare_to_baseline` 의 baseline 이 artifact 평균 → 잘못된 비교

**Mock 환경에서 안 보였던 이유**: synthetic data 는 `np.random.normal` — 깔끔한 정규분포. Real signal 의 *측정 외 sample* (transducer 분리, line flush) 없음.

**대응 권고**:
1. Tool 17–20 에 **physiological clipping** 추가 — MAP ∈ [20, 250] mmHg 같은 plausible 범위 밖 sample 은 NaN 으로 mask
2. 또는 별도 `sanitize_signal` preprocessor — `opsight/tools/signal_access_tools.py` 에 helper 추가
3. plan_1.3.5 task 1 의 task 1 (env verification) 처럼 *cohort 사전 분석* 으로 artifact 비율 파악 필요
4. `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]` — physiological plausibility range 의 임상적 적절성

### 🔴 Issue 2: Graph 는 streaming 아님 — *전체 signal* 한 번 주입

**관찰**: `build_graph(fm, signal=...)` 는 signal dict 를 한 번 받음. 매 tick 마다 SimClock 만 advance, signal 자체는 *전체 trajectory* 보유. FM tool / Signal Access tool 이 통계 계산 시 *t 이후 data 도 numpy array 에 포함* 됨.

**왜 leakage 안 되는가**: SimClock 의 `assert_le(query_window_end_s)` 가 `request.sim_time_s > clock.now_s` 만 체크. 그러나 tool 내부의 `_to_numpy(signal[k])` 가 *전체 array* 를 반환 → `np.mean(arr)` 등이 미래 sample 포함.

**즉**: 본 prototype 의 "real-time" 은 사실상 *retrospective full-trajectory* 처리. 진짜 streaming 이 아님.

**영향**:
- Trigger 가 이상함: 본 case 의 4500s hypotension 정보 가 t=30s 부터 *이미 통계에 영향*. mock data 는 30초만 sample 했으므로 안 보임.
- Faithfulness 평가 시 "이 brief 가 t=N 시점 까지의 정보 만 사용" 주장 위반 가능

**대응 권고** (Stage 2 작업):
1. `build_graph` 가 signal *slicer* 받도록 변경 — tool 호출 시 `clock.now_s` 까지 slice 한 view 전달
2. 또는 매 tick 마다 graph 재build (느림, 임시방편)
3. `opsight/sim_clock.py::slice_signal(signal, end_s, sampling_rate_hz)` helper 추가 + tool dispatch 에 적용

본 issue 는 *prototype 의 알려진 simplification* — `docs/project_brief.md §10` "simulated real-time" 의 strict 해석이 가능하나 현재 코드 는 약하게 구현.

### 🟠 Issue 3: Sampling rate mismatch — FM config 와 real interval 정합 필요

**관찰**: 우리 Mock FM 기본 `sampling_rate_hz=500.0` (mock_rule_based.yaml). 그런데 `vitaldb.VitalFile.to_pandas(interval=1.0)` 는 1Hz signal 반환.

**문제**: Tool 5 `temporal_trend` / FM 의 hypotension slope 계산이 `slope * sampling_rate_hz * 60` 으로 분당 단위 변환. 1Hz signal 을 500Hz 로 가정하면 slope 가 *500× 잘못* 계산됨.

**현재 mitigation**: `run_real_case.py` 가 `interval` 인자에서 `sr_hz = 1.0/interval` 계산 후 FM config 에 명시적 override.

**대응 권고**:
1. ✅ Script 가 자동 매칭 (현재)
2. Mock FM 내부에서 signal 의 *길이 + sim_time* 으로 sampling rate 자동 추론 (강건성 향상)
3. Tool envelope 에 `sampling_rate_hz` field 추가 — 호출자가 명시

### 🟠 Issue 4: NaN ratio 매우 큼 (50–97%)

**관찰**:
```
Solar8000/HR        : nan=52.7%
Solar8000/ART_MBP   : nan=52.8%
Solar8000/NIBP_MBP  : nan=97.0%  ← cuff 측정은 정상적으로 5분 주기
Solar8000/PLETH_SPO2: nan=52.4%
BIS/BIS             : nan=0.0%
```

**원인**:
- Solar8000 native rate 가 ~0.5Hz (격번 sample) — 1Hz resample 시 alternating NaN
- NIBP_MBP 97% NaN = cuff 측정 주기 (~5분 1회) 의 정상 결과
- BIS 는 native 1Hz 이므로 NaN 0%

**영향**:
- Tool 3 `assess_signal_quality` 가 quality score 0.3 (high_nan_ratio) 반환 → `[Assessment confidence: LOW]` 자동 부착 (이건 정상 작동)
- Tool 18 `describe_signal` 의 `missing_ratio` 가 정확히 반영됨 ✅
- Tool 19 `assess_variability` HRV: NaN-safe 처리 ✅ (NeuroKit2 가 valid sample 만 사용)
- **그러나 NaN 50%+ 가 "데이터 부재" 가 아닌 "sampling 주기" 임을 LLM 은 모름** → brief 가 "신호 결손" 으로 잘못 해석 가능

**대응 권고**:
1. `interval=2.0` 또는 더 큰 값 사용 — Solar8000 의 native rate 매칭
2. 또는 signal access tool 이 NaN-strip 후 통계 계산 + meta 에 "sample interval native" 명시
3. Brief LLM prompt v2 에 "NaN ratio 50%+ 는 sampling 주기 영향 일 수 있음 — 무조건 결손 으로 단정 금지" 추가

### 🟠 Issue 5: Script bug (f-string format specifier syntax) — 발견 + 수정 완료

**관찰**:
```python
f"mean={np.nanmean(arr):.2f if not np.isnan(np.nanmean(arr)) else float('nan')}"
# ValueError: Invalid format specifier
```

**원인**: Python f-string 의 format specifier 안에 ternary 못 씀. 사전 변수 할당 필요.

**수정 완료**: `scripts/run_real_case.py` 의 `df_to_signal_dict`:
```python
mean_val = float(np.nanmean(arr))
mean_str = f"{mean_val:.2f}" if not np.isnan(mean_val) else "NaN"
print(f"... mean={mean_str}")
```

### 🟠 Issue 6: Windows cp949 콘솔 UnicodeEncodeError — 발견 + 수정 완료

**관찰**:
```
UnicodeEncodeError: 'cp949' codec can't encode character '—' in position 73
```
- '—' (em dash, U+2014) — 한글 brief 에 포함된 LLM placeholder 출력
- Windows 기본 콘솔이 cp949 → UTF-8 외 문자 fail

**수정 완료**: `scripts/run_real_case.py` 가 stdout/stderr 을 UTF-8 wrapper 로 강제:
```python
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
```

**근본적 fix**: `PYTHONIOENCODING=utf-8` 환경변수 권장. 또는 `chcp 65001` 명령. 본 script 는 자체 fix 로 user 가 시도하기 좋게.

### 🟡 Issue 7: First-time VitalDB download 느림 (network dep)

**관찰**: `vitaldb.VitalFile(1, ...)` 첫 호출 시 ~2 초. 본 시점에서는 cached. 새 case_id 호출 시 download 다시.

**영향**: 100-case batch e2e 시 ~3 분 (case 당 2초 × 100). Network 의존.

**대응 권고**:
- `vitaldb` library 의 local cache 활용 (`~/.vitaldb_cache/`)
- 또는 별도 prefetch script — sample case 미리 다운로드

### 🟡 Issue 8: NIBP_MBP alias 가 ABP fallback 으로 자동 사용 안 됨

**관찰**: `signal` dict 에 `ABP` 와 `Solar8000/NIBP_MBP` 가 동시에 있음. Tool 17 의 ABP alias 순서는:
```python
_ABP_ALIASES = ("ABP", "MAP", "SNUADC/ART", "Solar8000/ART_MBP",
                "EV1000/ART_MBP", "Solar8000/NIBP_MBP", "Solar8000/FEM_MBP")
```
→ 첫 매칭 "ABP" 가 hit. NIBP 는 fallback 으로 안 감.

**문제**: ABP (case 1 의 ART_MBP, 53% NaN) 만 사용. NIBP_MBP (97% NaN 이지만 *실측 값은 정확*) 의 정보가 무시됨.

**대응 권고**: ABP 가 NaN 인 시점에는 NIBP 사용 — *time-aware fallback*. 현재 alias 시스템은 *전체 array* 매칭만 가능. Signal Access tool 17 의 sub-window per-field fallback 로직 추가 필요.

---

## 종합 평가

### ✅ 작동 확인

- Real VitalDB case 로 dual-mode graph 가 **end-to-end 작동**
- 9-section 한글 brief 정상 생성 + `[CLINICIAN-REVIEW]` marker 보존
- Leakage error 0 (envelope guard 작동)
- Trace JSONL 정상 저장
- Mock FM (rule-based) + 7 modality (HR / ABP / NIBP / SpO2 / EtCO2 / BT / BIS) 통합

### ⚠️ Prototype 한계 (mock data 만으로는 안 보였던)

- Sensor artifact pre-processing 부재 (Issue 1)
- Whole-signal injection — 진짜 streaming 아님 (Issue 2)
- Sampling rate 자동 매칭 필요 (Issue 3)
- NaN ratio 의 sampling 주기 vs 결손 구분 (Issue 4)

### 🟢 Stage 2 / 후속 작업 권고

1. **`opsight/preprocessing/`** 신규 module — sensor artifact clip + sampling rate detect + NaN-aware fallback
2. **Streaming signal slicer** — graph 가 매 tick 마다 sim_time 까지의 view 만 보도록
3. **Real-case batch test** — `tests/integration/test_e2e_real_cohort_10cases.py` (manifest 첫 10 case 로 e2e)
4. **Cohort artifact 통계** — `scripts/build_cohort.py` 에 modality 별 artifact 비율 (negative MAP, MAP > 250 등) 추가

### 임상의 검토 권고

- `[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요]`:
  - MAP / HR / SpO2 / EtCO2 physiological plausibility range
  - NIBP cuff 측정 주기 vs ABP continuous 의 정합 정책
  - case 1 (age 77, general surgery) 의 induction phase 패턴 정상 여부

---

---

## Mitigation — `opsight/preprocessing/` 추가 (2026-05-18)

### 산출물

- **`opsight/preprocessing/`** 신규 module (4 파일):
  - `signal_config.py` — 11 modality 의 physiological range / sampling rate / NaN gap 정책 (`SignalConfig` dataclass + alias map)
  - `artifact.py` — `clip_to_physiological()` (Issue #1) + `fill_short_nan_gaps()` (Issue #4)
  - `sampling.py` — `detect_sampling_rate()` + `resample_numpy()` (NaN-preserving)
  - `pipeline.py` — `preprocess_signal_dict()` end-to-end + `PreprocessReport`
- **Reference**: BFM (`Biosignal-Foundation-Model`) 의 `data/parser/{_common.py, _quality_checks.py, vitaldb.py}::SignalConfig` 패턴 *minimum subset* 포팅 — filter / peak detection / autocorrelation 같은 heavy 부분은 prototype scope 밖 (FM tool / Tool 19 가 cover).
- **Tests**: `tests/test_preprocessing.py` — **23 신규 test** (모두 통과)
- **`scripts/run_real_case.py`** — preprocessing 통합 (`--preprocess` default ON, `--no-preprocess` opt-out)

### Case 1 효과 (30 tick × 60s sim)

| Metric | Before (no preprocess) | After (preprocess) | 효과 |
|--------|----------------------|-------------------|------|
| HR signal quality | 0.30 | **0.95** | LOW → HIGH |
| Assessment confidence | LOW | **HIGH** | 정상화 |
| 저혈압 risk (induction) | 0.40 | **0.00** | artifact 영향 제거 |
| ABP samples clipped | 0 | **436** (3.78%) | −9 mmHg / 344 mmHg artifact 제거 |
| BT samples clipped | 0 | **1,176** (10.19%) | warm-up 전 cold reading 제거 |
| NaN gap filled (HR) | 0 | **5,453** | sampling 격번 NaN 거의 모두 채움 |
| NaN gap filled (ABP) | 0 | **4,982** | |

→ Issue #1 (artifact) + Issue #4 (NaN ratio) **두 가지 동시 해결**. Real VitalDB 데이터로 brief 의 정량 source 가 *임상적으로 의미 있는* 통계 기반이 됨.

### 누적 test

Sprint 5 시작 169 → preprocessing 추가 후 **239 pass + 1 skip** (+71 누적).

### 미해결 후속 (Stage 2)

- **Issue #2 (whole-signal injection)** — 여전히 prototype 한계. Streaming slicer 가 Stage 2 작업.
- **Issue #3 (sampling rate)** — script 의 자동 매칭 + `sampling.detect_sampling_rate()` 로 mitigated. Tool envelope 자체에 `sampling_rate_hz` field 추가는 ToolEnvelope v2 (별도 ADR) 검토 필요.
- **Issue #8 (time-aware NIBP fallback)** — 본 preprocessing 은 *전체 array* 처리. Per-window fallback (ABP NaN 시점 → NIBP) 은 별도 logic 필요 (Stage 2).
- BFM 의 *filter / spike detection / autocorrelation* 같은 heavy 부분은 본 prototype 에 포팅 안 됨. Real FM 합류 시 FM 의 latent representation 이 그 역할 (BFM 내부 기능).

---

## Sample run 명령

```bash
# Quick (5 ticks)
python scripts/run_real_case.py --case-id 1 --max-ticks 5

# Longer (30 min sim)
python scripts/run_real_case.py --case-id 1 --max-ticks 30 --tick-sim-advance-s 60

# Higher rate (5Hz)
python scripts/run_real_case.py --case-id 1 --interval 0.2 --max-ticks 10
```

산출물: `data/runs/case<id>_<timestamp>.{jsonl,summary.json}`.
