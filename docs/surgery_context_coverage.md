# Surgery Context Coverage Report (plan_1.5)

> 자동 생성 — `docs/surgery_context.yaml` 의 named category 가 cohort 의 몇 %를 cover 하는지.
> Source: `data/cohort/manifest.parquet` (5,946 cases, Sprint 5 build).

---

## Coverage 표

| Stratum | Named in `surgery_context.yaml` | Cohort n | Cohort % |
|---------|---------------------------------|----------|----------|
| `general` | ✅ | 4,539 | 76.3% |
| `thoracic` | ✅ | 1,071 | 18.0% |
| `gynecology` | ✅ | 224 | 3.8% |
| `urology` | ✅ | 112 | 1.9% |
| `other` | — | 0 | 0.0% |
| **합계** | — | **5,946** | **100.0%** |

→ Named category coverage = **100.0%** (DoD 기준 ≥ 80% 충족).

## 해석

- VitalDB `department` 4-bucket 이 cohort 전체를 100% cover — `other` bucket 0.
- 본 결과는 `pre_phase3_findings.md §2` 의 finding 과 일치 (department 가 이미 정확한 axis).
- `optype` 11-bucket 은 *mid-granularity reference* 로 yaml 의 `optype_subcategories` 에 보존됨 — 향후 hint 정밀화 시 활용 가능.

## ⚠️ Caveat

- Urology n=112 (1.9%). brief §11.0 의 wide-CI 보고 정책 적용 대상 — hint 의 적용 시 statistical confidence 가 낮을 수 있다.
- Pediatric / ASA=6 default INCLUDE (plan_1.2). 회의 후 EXCLUDE 결정 시 cohort 재생성 + 본 report 재실행 필요.

[CLINICIAN-REVIEW: 이형철 교수님 그룹 검토 필요] — `surgery_context.yaml` 의 (type × phase) hint cell 12 개 모두.
