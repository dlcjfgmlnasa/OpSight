# Trigger 7-Rules — Shallow ↔ Deep 분기를 결정짓는 규칙

> Shallow tick 이 끝날 때마다 "지금 Deep 으로 갈까?" 를 판단하는 결정론적 함수가 있다. **7개의 규칙 + 60초 cooldown** 으로 구성된다. LLM 이 결정하지 않는다.

## 왜 rule 인가, 왜 LLM 이 아닌가

직관적으로는 "LLM 이 상황을 보고 Deep 으로 갈지 결정하면 안 되나?" 라는 생각이 든다. 안 되는 세 가지 이유:

- **환각 risk** — LLM 이 critical event 를 "괜찮네" 라고 잘못 판단하면 deep brief 가 발화하지 않고, 환자에게 직접적 위험이 된다.
- **Latency 예측 불가능** — LLM 이 매 tick 마다 다른 시간이 걸리면 30초 budget 을 짤 수 없다.
- **검증 불가능** — unit test 로 "이 신호 패턴에 trigger 가 발화하는가" 를 확정짓기 어렵다.

그래서 trigger 는 **결정론적 Python 함수** 다. 같은 state 가 들어오면 항상 같은 결정. 코드: `vitalagent/triggers.py::should_escalate(state)`.

## 7개 규칙을 풀어 쓰면

각 규칙은 state 의 어떤 측정치를 보고, 임계치를 넘으면 Deep 으로 가야 한다고 신호를 보낸다.

**1. Hypotension risk 가 높을 때 (≥ 0.7)**
가장 흔한 발화 조건이다. FM 이 예측한 저혈압 발생 risk 가 0.7 을 넘으면 즉시 Deep.

**2. Risk 가 급상승할 때 (Δ ≥ 0.3 in 30s)**
risk 가 절대값으로 낮아도 *빠르게 올라오면* 발화. 30초 안에 0.3 이상 상승하는 패턴.

**3. 신호 품질이 갑자기 떨어졌을 때 (drop ≥ 0.3)**
ABP 가 NaN 으로 채워지거나 노이즈가 갑자기 심해지는 등. quality 평균이 0.3 이상 하락하면 Deep 으로 가서 어느 modality 가 망가졌는지 자세히 보고.

**4. 신호들 사이에 불일치가 보일 때 (consistency < 0.4 & 평균 quality ≥ 0.7)**
ABP 와 ECG 가 서로 다른 이야기를 할 때. 단 신호 품질 자체가 낮으면 (모두 noise 면) 발화하지 않는다 — 진짜 불일치인지 그냥 깨진 신호인지 구분.

**5. ★ Acute event — cardiac arrest risk > 0.5 (cooldown 우회)**
심정지 가능성이 잡힌다. 환자 안전이 절대 우선이라 60초 cooldown 을 무시하고 발화.

**6. ★ Clinician on-demand (cooldown 우회)**
사용자가 "지금 brief 보여줘" 를 명시적으로 요청. `state.scratch["clinician_on_demand"] = True` 가 set 되면 다음 tick 에서 즉시 Deep. 명시적 요청은 항상 우선.

**7. Periodic check — 마지막 deep 후 5분 경과**
아무 위험 신호가 없어도 5분에 한 번은 Deep brief 를 한다. 임상의가 "지금까지의 전체 그림" 을 받아볼 수 있도록.

## Cooldown — 연속 Deep 발화를 막는 60초 간격

위 규칙 중 하나가 fire 해서 Deep 이 발화한 직후, 60초 이내에 다시 같은 규칙이 발화하면 어떻게 될까? 매 tick 마다 Deep brief 가 쏟아져 나오면 임상의가 보기 힘들다.

그래서 **60초 cooldown** 을 둔다.

- 일반 규칙 (1, 2, 3, 4, 7) — cooldown 안이면 발화하지 않음
- **Acute event (5)** — 환자 안전 우선이므로 우회
- **Clinician on-demand (6)** — 명시적 요청 우선이므로 우회

## 평가 순서가 중요하다

`should_escalate(state)` 가 7개를 모두 평가하는 게 아니다. **우선순위 순서대로** 짧게 끊는다.

```python
def should_escalate(state) -> tuple[bool, str | None]:
    # 1. Clinician on-demand 가 가장 먼저 — 명시적 요청 우선
    if state.scratch.get("clinician_on_demand"):
        return True, "clinician_on_demand"

    # 2. Acute event — 환자 안전 우선 (cooldown 무시)
    reason = _check_arrest(state)
    if reason: return True, reason

    # 3. Cooldown gate — 여기서 부터 cooldown 적용
    if _within_cooldown(state):
        return False, None

    # 4. 나머지 trigger 들
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

코드 한 줄씩은 [[30_코드_워크스루/04_state_clock_triggers]].

## 임계치는 어디에 박혀 있나

모든 임계치는 모듈 최상단의 상수로 모아두었다. 임상의 검토 후 조정 가능하다.

```python
# vitalagent/triggers.py

HYPOTENSION_RISK_THRESHOLD: float = 0.7      # 규칙 1
RISK_DELTA_WINDOW_S: float = 30.0            # 규칙 2 — 윈도우
RISK_DELTA_THRESHOLD: float = 0.3            # 규칙 2 — 임계
QUALITY_DROP_THRESHOLD: float = 0.3          # 규칙 3
CONSISTENCY_THRESHOLD: float = 0.4           # 규칙 4 — 임계
CONSISTENCY_GOOD_QUALITY_GATE: float = 0.7   # 규칙 4 — gate
ARREST_RISK_THRESHOLD: float = 0.5           # 규칙 5
PERIODIC_CHECK_INTERVAL_S: float = 300.0     # 규칙 7 — 5분
DEEP_COOLDOWN_S: float = 60.0                # cooldown
```

⚠️ 모든 임계치에 `[CLINICIAN-REVIEW]` 마커. Mock FM Tier 2 의 발화 빈도 분석을 기반으로 임상의 그룹 검토 후 조정될 예정이다.

## "Clinician on-demand" 는 어떻게 켜지나

State 의 `scratch` dict 에 boolean flag 가 들어 있다.

```python
# 외부 orchestrator 또는 사용자 입력이 set:
state.scratch["clinician_on_demand"] = True

# 다음 _route 호출 시 1번 규칙이 즉시 fire → Deep
# Deep brief 발화 후 flag 가 자동 해제 (deep_brief.py 에서):
new_state.scratch["clinician_on_demand"] = False
```

임상의가 UI 에서 "지금 brief 보여줘" 를 누르면 다음 30초 tick 에서 Deep mode 로 전환된다.

## 실제로 어떻게 발화하나 — 100 case 결과

100 case 를 끝까지 돌려봤더니 (2026-05-16):

- `hypotension_risk_gt_0.7` 발화: **66회**
- `cross_modal_inconsistency_lt_0.4` 발화: **234회**
- 총 300회 deep fire (case 당 평균 3회)
- 100/100 case 에서 최소 1회 발화

발화 분포가 양호하다. 너무 자주 발화하면 (false alarm 폭주) 또는 거의 안 발화하면 (이벤트 누락) 임계치를 조정할 수 있다.

## Test 로 확정해둔 동작

`tests/test_triggers.py` 에 19개의 unit test 가 있다. 각 trigger 에 대해 *발화해야 할 경우* 와 *발화하지 말아야 할 경우* 의 쌍이 있고, cooldown semantic, on-demand bypass, no-data baseline 도 검증한다.

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

- [[Dual_mode_architecture]] — trigger 가 graph 의 conditional edge 위치에서 어떻게 호출되는가
- [[데이터_누수_방지]] — trigger 가 *과거 정보만* 사용하는 이유
- [[30_코드_워크스루/04_state_clock_triggers]] — `triggers.py` 코드 한 줄씩
