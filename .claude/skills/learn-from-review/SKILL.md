---
name: learn-from-review
description: Process code review feedback and add lessons to LESSONS.md. Use this skill when the user says "learn from review", "update lessons", "add to lessons", "what did we learn", or after receiving code review feedback from a human or automated reviewer. Also use when the user pastes review comments or says "the reviewer said..." or "the PR review found...". This skill ensures the same mistakes aren't repeated.
---

# Learn From Review

You process code review feedback — from humans, from Claude Code Review on GitHub, or from the local /code-review plugin — and distill it into actionable lessons in `.claude/LESSONS.md`.

## How to Use

The user can trigger this in several ways:

### 1. After a human review
The user tells you what the reviewer said:
- "The reviewer said we should always validate email format before saving"
- "My teammate pointed out we're not handling the case where the API returns null"

### 2. After Claude Code Review on GitHub
The user says "learn from the PR review" or "check the review comments." Use the GitHub CLI to read them:

```bash
# Get review comments on the current branch's PR
gh pr view --comments
# Or for a specific PR
gh pr view <PR-NUMBER> --comments
# Get inline review comments
gh pr view <PR-NUMBER> --json reviews,comments
```

Read through the findings, filter out noise, and extract the real lessons.

### 3. After running /code-review locally
The user runs the code-review plugin and asks you to learn from the results.

### 4. After a debugging session
The user (or you) fixed a tricky bug. Capture what went wrong and how to avoid it.

## Process

### Step 1: Understand the Feedback

Read the review comments. For each finding, determine:
- Is this a **real lesson** (something that should change future behavior)?
- Or is it a **one-off** (specific to this PR, not generalizable)?

Only add real lessons. Skip things like "typo on line 42" or "missing semicolon."

### Step 2: Categorize and Write

Add lessons to the appropriate section in `.claude/LESSONS.md`:

- **Coding Patterns** — "Always use X pattern for Y" or "Prefer X over Y because Z"
- **Mistakes to Avoid** — "Don't do X because Y happened"
- **Project-Specific Gotchas** — "The payment API returns 200 even on failure, check the response body"
- **Architecture Decisions** — "We chose X over Y because Z (decided [date])"

### Step 3: Format

Each lesson should be:
```markdown
- [date] [lesson in 1-3 lines, specific and actionable]
```

**Good examples:**
```markdown
- [2026-03-11] Always check for null responses from the /users API — it returns null instead of 404 when a user is deleted
- [2026-03-11] Don't use findOne() without a where clause in Prisma — it returns the first record in the table, not null
- [2026-03-11] Email validation must happen in the service layer, not just the route handler — the import endpoint bypasses route validation
```

**Bad examples:**
```markdown
- Be careful with the database (too vague)
- Fixed a bug (not a lesson)
- Use good variable names (too generic, not project-specific)
```

### Step 4: Prune if Needed

If LESSONS.md exceeds 150 lines:
1. Review all lessons
2. Remove any that are no longer relevant (e.g., about code that was deleted)
3. Merge duplicates
4. Archive removed lessons to `.claude/docs/archived-lessons.md` (create if needed)

### Step 5: Commit

```bash
git add .claude/LESSONS.md
git commit -m "docs: update lessons learned from code review"
```

## What Makes This Work

LESSONS.md is referenced in CLAUDE.md, so it gets read at the start of every session. Over time, the agent stops making mistakes it's made before. The compound effect is significant — after 10-20 reviews, the agent's output quality noticeably improves because it has a growing list of project-specific knowledge that no general model training could provide.
