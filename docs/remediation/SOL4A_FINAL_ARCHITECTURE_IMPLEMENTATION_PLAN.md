# SOL-4A Final Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind final retrieval identity and production verification to authoritative evidence adaptation and successfully executed factory-created backend instances.

**Architecture:** A sealed `AuthoritativeCorpus` is produced only by the EvidenceSpan adapter. A production factory registers concrete retriever instances and complete component identities in an internal trusted registry; successful retrieval creates run-scoped receipts that final comparison validates against corpus, query, backend, dependency, and output digests.

**Tech Stack:** Python 3.11+, frozen dataclasses, canonical JSON/SHA-256, weak-reference trusted registries, pytest, Git.

---

### Task 1: Freeze the acceptance boundary

**Files:**
- Create: `docs/remediation/SOL4A_FINAL_ACCEPTANCE_CONTRACT.md`
- Create: `docs/remediation/SOL4A_FINAL_ARCHITECTURE_IMPLEMENTATION_PLAN.md`

- [x] **Step 1: Record the authoritative adapter mapping, schema v3, numeric policy, strict fingerprint type, trusted factory, execution receipt, composite dependencies, final boundary, blockers, and adversarial checks.**
- [x] **Step 2: Confirm the contract excludes SOL-4B and freezes the next review scope.**

### Task 2: Authoritative corpus identity

**Files:**
- Create: `src/ecoquant/retrieval/corpus_adapter.py`
- Modify: `src/ecoquant/retrieval/base.py`
- Modify: `src/ecoquant/retrieval/kg.py`
- Test: `tests/research/test_retrieval_methods.py`
- Test: `tests/integration/test_pdf_manager_adapter.py`

- [x] **Step 1: Add failing tests for document/page/block identity, deterministic span conversion, missing document ID, handcrafted-final rejection, schema-v3 bytes, strict fingerprint syntax, and every NumPy scalar case.**
- [x] **Step 2: Run only those tests and confirm failures are caused by missing adapter/schema/validation behavior.**
- [x] **Step 3: Implement the sealed `AuthoritativeCorpus`, exact EvidenceSpan mapping, expanded `CorpusRecord`, schema-v3 serialization, strict fingerprint validator, and document-to-span graph index connection.**
- [x] **Step 4: Re-run the new identity tests and existing fingerprint/graph tests until green.**
- [x] **Step 5: Commit as `fix: bind retrieval corpus identity to normalized evidence` (`a421f71`).**

### Task 3: Backend provenance and execution receipts

**Files:**
- Create: `src/ecoquant/retrieval/provenance.py`
- Create: `src/ecoquant/retrieval/production_factory.py`
- Modify: `src/ecoquant/retrieval/base.py`
- Modify: `src/ecoquant/retrieval/dense.py`
- Modify: `src/ecoquant/retrieval/reranker.py`
- Modify: `src/ecoquant/retrieval/verifier.py`
- Modify: `src/ecoquant/retrieval/__init__.py`
- Test: `tests/integration/test_production_backends.py`
- Test: `tests/research/test_retrieval_methods.py`

- [x] **Step 1: Add failing hostile tests for fabricated methods/metadata/flags, copied backend identities, cross-corpus/query/method receipts, constructor-only reranker, partial dense state, and incomplete composite chains.**
- [x] **Step 2: Run the hostile group and verify each expected RED failure.**
- [x] **Step 3: Implement immutable dependency identities, the factory-only instance registry, post-execution receipts, exact dependency-chain validation, and final comparison receipt checks.**
- [x] **Step 4: Move all production verification transitions to successful factory-registered execution and require dense/reranker/verifier runtime evidence.**
- [x] **Step 5: Re-run the hostile group and the complete focused SOL-4A suite until green.**
- [x] **Step 6: Commit as `fix: bind production verification to executed backends` (`42d1f9d`).**

### Task 4: Coordination and final evidence

**Files:**
- Modify: `.superpowers/remediation/task-5-7-final-report.md`
- Modify: root `docs/remediation/SOL_ACCEPTANCE_MATRIX.md`
- Modify: root `docs/remediation/SOL_WORK_LEDGER.md`
- Modify: root `docs/remediation/SOL4B_INTEGRATION_CONTRACT.md`
- Modify: root `portfolio-package/CODEX_TASK_LOG.md`

- [x] **Step 1: Run the exact focused suite and record 188 passed / 2 skipped without treating skips as verification.**
- [x] **Step 2: Update all coordination records with the third failed review, repair commits, frozen contract, exact results, blockers, and fresh-review requirement; declare no PASS/GO.**
- [ ] **Step 3: Commit EcoQuant documentation and root coordination separately without unrelated root files.**
- [ ] **Step 4: Run `git diff --check`, `git diff --stat`, `git status --short`, and the exact focused suite again before handoff.**
