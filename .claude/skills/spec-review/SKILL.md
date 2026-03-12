---
name: spec-review
description: Review an implementation against its spec to verify completeness and correctness. Use when the user asks to "review", "verify", "check", "validate" an implementation, or when implementation is complete and needs a final check. Also use when the user says "is this done?" or "did we cover everything?". This skill audits the implementation against the spec's acceptance criteria and tests.
---

# Spec Review

You are a quality assurance agent. Verify that an implementation matches its spec completely and correctly.

## Process

### Step 1: Load Context Efficiently

1. Read the spec from `.claude/specs/`
2. Read progress.md to understand what was implemented and any known issues
3. Get the list of changed files via `git diff main --name-only` (or appropriate base branch)
4. Do NOT read every changed file upfront — audit criterion by criterion

### Step 2: Acceptance Criteria Audit

For EACH acceptance criterion in the spec, use a subagent to verify:

1. **Is there code that implements this?** Search for the relevant code path.
2. **Is there a test that verifies this?** Search for the corresponding test.
3. **Does the test verify real behavior?** Read the test assertions — are they checking actual outcomes?

Build a checklist:

```
### Story 1: [Title]
- AC1: GIVEN x WHEN y THEN z
  - Implementation: ✅ / ❌ / ⚠️ [brief note]
  - Test exists: ✅ / ❌
  - Test quality: ✅ / ❌ / ⚠️ [brief note]
```

### Step 3: Run Tests

Execute the full test suite. Report pass/fail counts and any failures.

### Step 4: Out-of-Scope Check

Read the spec's "Out of Scope" section. Spot-check that nothing listed there was implemented. Check for scope creep.

### Step 5: Report

```
## Spec Review: [Feature Name]

### Summary
- Stories: X/Y implemented
- Acceptance criteria: X/Y met
- Tests: X written, X passing
- Regressions: none / [list]

### Issues Found
1. [what's missing or wrong]

### Recommendations
1. [what to fix]

### Verdict: PASS / NEEDS WORK
```

If NEEDS WORK, offer to fix issues using `/spec-implement`.

Update progress.md with the review results.
