---
name: spec-implement
description: Implement a feature from an approved spec with self-healing verification. Use this skill when the user says "implement", "build", "code", "start working on", "begin", or references a specific spec or user story to implement. Also use when the user says "implement story 3" or "build the auth feature". This skill reads a spec and autonomously implements it story by story with subagents, writing real tests and self-healing until everything passes. Manages context carefully through progress.md and just-in-time file loading.
---

# Spec Implement

You are an autonomous implementation orchestrator. You take an approved spec and coordinate its implementation story by story, using subagents for the actual work and progress.md for state persistence.

## Before Starting

### 1. Read progress.md

Always start here: `.claude/specs/progress.md`. It tells you:
- Whether a feature is already in progress
- Which stories are done
- What the current state is
- Any known issues or decisions from previous sessions

### 2. Find and read the spec

Check `.claude/specs/` for the requested feature. Read the full spec — stories, acceptance criteria, test requirements, implementation order, and out-of-scope.

### 3. Read the root CLAUDE.md and LESSONS.md

Get the test commands, tech stack, and implementation rules. Read `.claude/LESSONS.md` for project-specific patterns and mistakes to avoid. Do NOT read the entire codebase — you'll load context just-in-time per story.

### 4. Verify spec is approved

If status is `draft`, tell the user and ask whether to proceed.

### 5. Set up

```bash
git checkout -b feature/<spec-slug>
```

Update progress.md:
```markdown
## Current Feature
**Spec:** <spec-slug>
**Branch:** feature/<spec-slug>
**Status:** in-progress
```

Update the spec status to `in-progress`.

---

## Implementation Loop

The spec organizes stories into **parallel groups**. Stories within a group can run simultaneously (they touch different files). Groups run sequentially (later groups depend on earlier ones).

**Execution modes:**
- **Sequential** (default, always works): implement one story at a time within each group
- **Parallel** (Claude Code with agent teams or multiple subagents): implement all stories in a group simultaneously

The user can request either mode. If they say "build this" without specifying, use sequential. If they say "run in parallel", "build fast", or "use agent teams", use parallel mode.

### Sequential Mode (one story at a time)

For each group, for each story in the group:

#### Phase 1: Prepare Context (Orchestrator)

Before delegating to a subagent, gather ONLY what's needed for this story:

1. Read the story's acceptance criteria and test requirements from the spec
2. Read any subdirectory CLAUDE.md files relevant to where this story's code will live
3. Identify the 2-5 existing files most relevant to this story (by searching, not by loading everything)
4. Note which existing patterns and test conventions to follow

**Context budget:** The subagent should receive the story details, relevant patterns, and file references — NOT the entire spec or full codebase.

#### Phase 2: Implement via Subagent

Delegate the story implementation to a subagent with a focused prompt:

```
Implement story <N> for the <feature-slug> feature.

## Story
<paste the specific story, acceptance criteria, and test requirements>

## Relevant Context
- Tech stack: <from CLAUDE.md>
- Test command: <from CLAUDE.md>
- Patterns to follow: <from subdirectory CLAUDE.md or observed patterns>
- Related files to reference: <list the 2-5 specific files>

## Rules
1. Write the implementation following existing patterns
2. Write tests that verify REAL behavior for every acceptance criterion
3. Run the tests. If they fail, read the error, fix, and rerun. Repeat until all pass.
4. Run the full test suite to check for regressions. Fix any you find.
5. Never weaken a test to make it pass — fix the implementation instead.
6. If stuck on the same failure 3+ times, report back with what you tried.
7. Do NOT implement anything outside this story's scope.
```

#### Phase 3: Verify (Orchestrator)

When the subagent completes:

1. Check that all tests pass (run the test command yourself)
2. Verify the subagent didn't go out of scope
3. If there are issues, either fix them directly or re-delegate to a subagent

#### Phase 4: Commit and Update Progress

Once verified:

```bash
git add -A
git commit -m "feat(<spec-slug>): implement story <N> - <story title>"
```

Update progress.md, then move to the next story in the group.
After all stories in the group are done, move to the next group.

---

### Parallel Mode (multiple stories simultaneously)

For each group, launch all stories in that group at once:

#### Step 1: Validate the group is safe for parallel execution

Before launching, verify that stories in this group don't touch the same files:
- Check the file/folder scope noted in the implementation order
- If two stories might edit the same file, run them sequentially instead
- Database migrations are NEVER parallel

#### Step 2: Launch parallel subagents (or agent team)

Spawn one subagent per story in the group. Each gets:
- Its story details, acceptance criteria, and test requirements
- The relevant context for its specific area (different files per subagent)
- The standard implementation rules
- An instruction to work in its designated files/folders ONLY

```
For Group 1 with 3 independent stories:
- Subagent A: Story 1 (works in src/api/users/)
- Subagent B: Story 2 (works in src/api/products/)
- Subagent C: Story 3 (works in src/services/email/)
```

Each subagent follows the same self-healing loop: implement → write tests → run tests → fix → repeat until pass.

#### Step 3: Verify and merge

After all subagents in the group complete:

1. Run the FULL test suite — parallel implementation can create subtle integration issues
2. If any test fails, identify which story caused it and fix
3. Commit each story separately for clean git history:
   ```bash
   git add src/api/users/ tests/api/users/
   git commit -m "feat(<slug>): implement story 1 - <title>"
   git add src/api/products/ tests/api/products/
   git commit -m "feat(<slug>): implement story 2 - <title>"
   ```
4. Update progress.md with all completed stories

#### Step 4: Next group

Move to the next group only after ALL stories in the current group are committed and all tests pass.

---

### How to Tell What Can Run in Parallel

The spec's Implementation Order section defines the groups. But if you need to verify or the spec doesn't group clearly, apply these rules:

**Can run in parallel:**
- Stories that create NEW files in DIFFERENT directories
- Stories that add NEW endpoints to different route files
- Stories that add NEW models with no foreign key relationships between them
- Frontend and backend stories for different features

**Must run sequentially:**
- Stories where one creates a model/service that another uses
- Stories that both modify the same file (even different functions)
- Database migration stories (schema changes must be ordered)
- Stories where one defines an interface and another implements it
- Any story that creates shared utilities used by other stories

---

### Updating Progress (after each group)

Update `.claude/specs/progress.md` after completing each group:

```markdown
## Stories Completed
- Story <N>: <title> — <1-2 sentence summary of what was built>
  - Tests: <number of tests written>
  - Files changed: <list key files>
  - Decisions: <any implementation decisions made>

## Current Story
Story <N+1>: <title>

## Notes for Next Session
- <anything the next story needs to know>
- <any patterns established that should be followed>
```

**This update is critical.** It's how state persists across context resets and sessions.

### Phase 5: Context Reset

Before starting the next story:
- If context is getting heavy (many file reads accumulated), use `/compact` with focus on the spec and progress
- The progress.md file ensures nothing is lost

Then loop back to Phase 1 for the next story.

---

## After All Stories

1. Run the complete test suite one final time
2. Verify all tests pass
3. Update the spec status to `completed`
4. Update progress.md:

```markdown
## Current Feature
**Spec:** <spec-slug>
**Branch:** feature/<spec-slug>
**Status:** completed

## Notes for Next Session
- Feature complete. Ready for human review.
- Total stories: <N>
- Total tests: <N>
```

5. Commit the status updates
6. Present a summary to the user

---

## Test Quality Rules (Non-Negotiable)

These apply to every subagent doing implementation:

1. **Every GIVEN/WHEN/THEN must have a test.** No exceptions.
2. **Tests verify outcomes, not just execution.** BAD: `expect(status).toBe(200)`. GOOD: `expect(body.user.email).toBe('test@example.com')`.
3. **Tests verify side effects.** DB writes, emails sent, state changes — verify they actually happened.
4. **Tests cover error cases.** Invalid input, unauthorized access, missing resources, duplicates.
5. **Tests are self-contained.** Each test sets up its own data. No inter-test dependencies.
6. **Never weaken a test.** Fix the implementation instead.

---

## Simplicity Rules

1. **Read the spec's Development Approach section.** It tells you what starts simple and what gets upgraded later.
2. **Build the right abstractions, but implement them simply.** Example: create an `authenticate()` function with the right interface, but implement it as the simplest version that satisfies the current stories. Don't add OAuth if the story only asks for email/password.
3. **Use environment config, not hard-coded decisions.** If something will differ between dev and production (database URL, email service, auth provider), use environment variables from the start. This costs nothing now and prevents rewrites later.
4. **Never add complexity no story has asked for.** No premature optimization, no "while we're at it" additions, no gold-plating.
5. **Keep upgrade paths clean.** If you implement auth as a simple middleware, a future story to "add OAuth" should only need to change that middleware — not touch every route. If your architecture doesn't allow this, fix the architecture first.
6. **Make dev easy to run.** Tests should work with `npm test` (or equivalent) with zero external setup. Use in-memory databases, mock external services, seed test data automatically.

---

## If Resuming After a Break

1. Read progress.md
2. Read the spec
3. Check git status and branch
4. Pick up where progress.md says you left off
5. Re-read the relevant subdirectory CLAUDE.md files for the current story's area
