# Practice — The 7 Judgement Rules

Researcher-facing rules for practice annotation. The researcher must be able
to explain these in their own words before the formal pilot starts.

---

## 1. SUPPORTED

**Definition:** Every mandatory requirement is covered by evidence, the
evidence is time-valid and version-valid, and any derived answer is
reproducible from the evidence.

**Example:** "AAPL operating cash flow minus capex for FY2024" — we see the
OCF fact, the capex fact (same company, same period, same unit), both filed
before the cutoff, and 118.548 − 44.477 = 74.071.

## 2. PARTIAL

**Definition:** Some but not all requirements are met. A key input is missing,
or a period/unit/scope is only partially compatible.

**Example:** "Working capital" asks for current assets − current liabilities,
but only current assets is disclosed. The evidence covers half the requirement.

## 3. CONFLICTING

**Definition:** Evidence items disagree on a value for the same identity
(concept + period + unit + version). Often an original vs amended filing.

**Example:** AccruedLiabilitiesCurrent = 3,376M (10-K) vs 3,852M (10-K/A) for
the same period. The two numbers conflict until the latest is resolved as
authoritative.

## 4. INSUFFICIENT

**Definition:** Required evidence is absent — a metric is not reported, or a
needed input is missing. Without a human-audited negative certificate, this is
TOOLING_BLOCKED, not a gold ABSTAIN.

**Example:** A concept AAPL does not report in that fiscal year → no fact
exists → not answerable from the disclosed set.

## 5. WRONG PERIOD

**Definition:** The evidence's fiscal period does not match the question's
target period (different fiscal year, or duration vs instant mismatch).

**Example:** Question asks FY2024 but the retrieved fact is FY2023. The
period is wrong even if the metric and company are right.

## 6. FUTURE SOURCE

**Definition:** The evidence was filed AFTER the source cutoff. A system using
it would be leaking post-cutoff information.

**Example:** A filing dated 2026-05-01 used to answer a question with cutoff
2025-12-31. Future source — must be excluded.

## 7. VERSION SUPERSESSION

**Definition:** A document version supersedes/amends an earlier one. The
latest valid version wins; the superseded value must not be used as final.

**Example:** A 10-K/A restates a 10-K value. The 10-K value is superseded for
the final answer, but the conflict is recorded.

---

## How to apply in practice

For each case ask:

1. What exactly is the question asking? (metric, period, unit, scope)
2. Is the original source present and exact?
3. Does the evidence cover ALL requirements, or only some?
4. Are the period/unit/scope compatible across evidence?
5. Is any answer reproducible from the evidence?
6. Is there a version conflict (amendment/restatement)?
7. Was any source filed after the cutoff?

Decision: ANSWER only if SUPPORTED. REVIEW if PARTIAL/CONFLICTING/wrong
period/future source/version supersession needs judgement. ABSTAIN if
INSUFFICIENT (negative, certificate-backed) or unanswerable.
