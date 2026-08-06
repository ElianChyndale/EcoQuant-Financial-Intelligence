# Workbench Human-Factors Design

**Date:** 2026-08-06

## Layout

One case per screen. Three sticky panels:

```
┌───────────────────┬─────────────────────────┬─────────────────┐
│ Question          │ Original Evidence       │ Human Judgement │
│ Frozen metadata   │ Text/Table/XBRL/Version │                 │
│ Requirements      │                         │                 │
├───────────────────┴─────────────────────────┴─────────────────┤
│ Neutral mechanical checks                                    │
└───────────────────────────────────────────────────────────────┘
```

The judgement panel stays visible while evidence is reviewed.

## Progressive disclosure

Default: question, frozen metadata, candidate evidence, local excerpts,
essential table rows/XBRL facts, mechanical checks. Expansion available for
preceding/following context, full section/table, adjacent rows/columns, other
periods, original vs amended, related XBRL, local search.

## Minimized human input

Immutable fields (case ID, queue, reviewer, cutoff, question, candidate
evidence IDs, interface condition, blind temp ID) are prepopulated and
non-editable. Extracted metadata is shown with CONFIRM/EDIT/UNCERTAIN. No
manual evidence-ID typing (checkboxes), no manual JSON.

## Evidence selection

Two distinct checkbox concepts: SUPPORTING (relevant) and MINIMAL (removal
makes support incomplete unless an equivalent replacement exists). Neither is
auto-selected. `MINIMALITY_UNCERTAIN` allowed. Descriptive warnings when
minimal ⊄ supporting, nothing selected, duplicates present, or a mandatory
requirement has no selection.

## Short rationale

One to three sentences, human-written. No autocomplete, no generated
suggestions, no case-specific templates. General placeholder only.

## Keyboard

A/R/X = ANSWER/REVIEW/ABSTAIN · S/P/C/I/U = sufficiency levels · 1-5 =
confidence · J/K = evidence nav · E = expand · Space = select · Ctrl+S =
save · Ctrl+Enter = open final review. **Signing has no shortcut** — explicit
typed `SIGN <case-key>` required.

## Fatigue support

Non-blocking "Five records completed. Consider a short break." every 5 signed
records. Tracks (without interpreting) median active time, unresolved count,
low-confidence count, evidence expansions, corrections. Flags suspicious
patterns (extremely short time, repeated immediate signing, all-confidence-5,
empty rationales) for private attention — never auto-modifies labels.

## Accessibility

High-contrast, resizable panels, keyboard nav, visible focus, accessible
labels, no colour-only meaning, responsive for standard laptops, optional
compact mode. UI helper text may include Chinese; stored labels/enums remain
frozen English schema.
