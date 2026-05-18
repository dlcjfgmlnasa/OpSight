# Trigger 7-Rules — Shallow ↔ Deep 분기 결정

> 7개 규칙 + 60초 cooldown. **rule-based, LLM-driven 아님** (brief §13.3).

## 왜 rule, 왜 LLM 이 아닌가

LLM 이 trigger 결정 시:
- **환각 risk** — critical event 를 "괜찮네" 라 잘못 판단 → 환자 위험
- **Latency 예측 불가** — 매 tick 다른 시간
- **Unit test 어려움** — stochastic

→ 결정론적 Python 함수 `should_escalate(state)` 가 분기. 코드: `opsight/triggers.py`.

## 7 rules

(brief §6.3 정확 일치)

| # | Rule | 발화 조건 | Cooldown 우회 |
|---|------|----------|---------------|
| 1 | **Hypotension risk** | 최근 hypotension risk > 0.7 | ❌ |
| 2 | **Rapid risk increase** | Δ > 0.3 within 30s | ❌ |
| 3 | **Signal quality drop** | 평균 quality 하락 > 0.3 | ❌ |
| 4 | **Cross-modal inconsistency** | consistency < 0.4 & avg quality ≥ 0.7 | ❌ |
| 5 | **Acute event — arrest** | cardiac arrest risk > 0.5 | ✅ |
| 6 | **Clinician on-demand** | `state.scratch["clinician_on_demand"] == True` | ✅ |
| 7 | **Periodic check** | 마지막 deep 후 5분 경과 | ❌ |

Rule 4 의 quality gate (≥ 0.7) 가 있는 이유: 모든 신호가 noise 면 진짜 불일치인지 깨진 신호인지 구분 불가.

## Cooldown — 60초

연속 deep 발화 방지. 일반 rule (1, 2, 3, 4, 7) 은 cooldown 안에선 fire X.

**우회**:
- Rule 5 (acute event) — 환자 안전 우선
- Rule 6 (clinician on-demand) — 명시적 요청 우선

## 평가 순서 — `should_escalate(state)`

```python
def should_escalate(state) -> tuple[bool, str | None]:
    # 1. Clinician on-demand — always honored
    if state.scratch.get("clinician_on_demand"):
        return True, "clinician_on_demand"

    # 2. Acute event — bypass cooldown
    reason = _check_arrest(state)
    if reason: return True, reason

    # 3. Cooldown gate
    if _within_cooldown(state):
        return False, None

    # 4. Remaining triggers
    for check in (
        _check_hypotension,
        _check_rapid_increase,
        _check_quality_drop,
        _check_cross_modal_inconsistency,
        _check_periodic,
    ):
        reason = check(state)
        if reason: return True, reason

    return False, None
```

순서: **명시적 요청 → 환자 안전 → cooldown gate → 나머지**. [[30_코드_워크스루/04_state_clock_triggers]] 참조.

## Threshold 상수

```python
# opsight/triggers.py

HYPOTENSION_RISK_THRESHOLD: float = 0.7      # brief §6.3
RISK_DELTA_WINDOW_S: float = 30.0
RISK_DELTA_THRESHOLD: float = 0.3
QUALITY_DROP_THRESHOLD: float = 0.3
CONSISTENCY_THRESHOLD: float = 0.4
CONSISTENCY_GOOD_QUALITY_GATE: float = 0.7
ARREST_RISK_THRESHOLD: float = 0.5
PERIODIC_CHECK_INTERVAL_S: float = 300.0     # 5 minutes
DEEP_COOLDOWN_S: float = 60.0
```

⚠️ 모두 `[CLINICIAN-REVIEW]` — Mock FM Tier 2 fire 빈도 분석 후 임상의 조정 예정.

## 100-case e2e 결과 (2026-05-16)

Trigger 분포:
- `hypotension_risk_gt_0.7`: 66
- `cross_modal_inconsistency_lt_0.4`: 234
- 총 300 deep fire (case 당 평균 3회)
- 100/100 case 에서 최소 1회 발화

분포 양호. 너무 자주 / 거의 안 발화 시 threshold 조정.

## Clinician on-demand

`state.scratch["clinician_on_demand"]` flag.

```python
# 외부 orchestrator / UI 가 set:
state.scratch["clinician_on_demand"] = True

# 다음 _route 에서 rule 1 fire → Deep mode
# Deep brief 발화 후 flag 자동 해제 (deep_brief.py):
new_state.scratch["clinician_on_demand"] = False
```

UI 에서 "지금 brief 보여줘" → 다음 30s tick 에서 Deep.

## Unit test — 19 test (`tests/test_triggers.py`)

각 trigger 의 positive + negative 쌍 + cooldown semantics + on-demand bypass + no-data baseline.

```
test_trigger_hypotension_positive                                   PASSED
test_trigger_hypotension_negative_low_risk                          PASSED
test_trigger_rapid_increase_positive                                PASSED
test_trigger_rapid_increase_negative_small_delta                    PASSED
test_trigger_quality_drop_positive                                  PASSED
test_trigger_quality_drop_negative_no_drop                          PASSED
test_trigger_inconsistency_positive                                 PASSED
test_trigger_inconsistency_negative_low_quality_gate                PASSED
test_trigger_arrest_positive                                        PASSED
test_trigger_arrest_negative_low_risk                               PASSED
test_trigger_clinician_on_demand_positive                           PASSED
test_trigger_clinician_on_demand_bypasses_cooldown                  PASSED
test_trigger_periodic_positive_first_check                          PASSED
test_trigger_periodic_positive_after_last_deep                      PASSED
test_trigger_periodic_negative_too_early                            PASSED
test_cooldown_blocks_non_acute_triggers                             PASSED
test_cooldown_bypassed_by_arrest                                    PASSED
test_cooldown_expires_after_60s                                     PASSED
test_no_data_does_not_fire                                          PASSED

19 passed
```

## 다음 노트

- [[Dual_mode_architecture]] — trigger 가 conditional edge 위치
- [[데이터_누수_방지]] — trigger 가 *과거 정보* 만 사용
- [[30_코드_워크스루/04_state_clock_triggers]] — `triggers.py` 워크스루
