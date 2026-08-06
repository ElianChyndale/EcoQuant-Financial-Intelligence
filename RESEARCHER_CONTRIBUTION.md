# Researcher Contribution Statement

**Date:** 2026-08-06
**Author:** Elian (researcher)

This document distinguishes researcher-owned work from AI-assisted work in the
FinVEST research programme.

---

## Researcher-owned

The following are the researcher's substantive contributions and are not
delegable to an AI:

- **Problem formulation** — the central research question (minimum sufficient,
  version-valid, executable evidence sets) and the research boundaries.
- **Scientific decisions** — hypothesis selection, primary metric choice,
  statistical design (clustered bootstrap, Holm correction, preregistration
  rules), Go/No-Go criteria.
- **Manual annotations** — human gold labels, evidence-set judgments,
  adversarial-case review, human-study labels (entered and signed by humans).
- **Failure interpretation** — reading negative results (e.g. E5 leakage
  impact, E1 method reversal) and deciding what they mean.
- **Final claims** — approving every claim that appears in the paper, CV, or
  public materials.
- **Financial definitions** — the finance-ontology terms, metric definitions
  (FCFF, ROIC, working capital conventions), and their assumptions.
- **Adjudication** — resolving annotation disagreements; the final gold label.
- **Paper argument** — the narrative, positioning against related work, and
  limitations.

## AI-assisted

The following were AI-assisted and are verified by tests/audits rather than
treated as researcher judgments:

- **Code scaffolding** — package structure, module interfaces.
- **Test generation** — unit tests; the researcher reviews the assertions.
- **Adapter implementation** — SEC/GRI-QA/FinanceBench data adapters.
- **Documentation drafts** — technical reports, dataset cards (researcher
  reviews and approves).
- **Runner orchestration** — one-command experiment runners and result
  artifacts.
- **Static audit suggestions** — e.g. the E5 gold-feature leakage detection;
  the researcher confirms and decides remediation.

## Principle

> AI-generated proposals become part of the research only after the researcher
> (or a human reviewer) tests, audits, or manually validates them. Nothing
> authored by AI is presented as a researcher judgment or as human-generated
> evidence.
