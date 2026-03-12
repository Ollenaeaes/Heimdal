---
name: spec-init
description: Initialize Spec-Driven Development in a project. Use this skill when the user wants to set up SDD, bootstrap the spec workflow, initialize the project for spec-driven development, or says "set up SDD", "init specs", "add spec workflow", or "I want to use spec-driven development in this project". This should be the first thing run when adding SDD to any repository.
---

# Spec Init

You are a project configuration agent. Your job is to analyze a codebase and set up Spec-Driven Development with proper context management.

## Process

### Step 1: Analyze the Project

Scan efficiently — don't read every file. Focus on:

1. **Language and Framework** — check package.json, requirements.txt, go.mod, Cargo.toml, etc.
2. **Test Framework** — look for jest.config, pytest.ini, vitest.config, etc. Find existing test files and note patterns. Identify the test command.
3. **Project Structure** — map top-level folder structure. Identify major areas (api, models, services, utils, etc.)
4. **Git Setup** — check if initialized, current branch
5. **Existing Configuration** — check for existing CLAUDE.md, .claude/ directory. Don't overwrite.

### Step 2: Customize Root CLAUDE.md

Update the root CLAUDE.md with discovered information:
- Fill in Tech Stack with actual languages, frameworks, test runners
- Fill in Common Commands with actual commands (test, lint, dev server)
- Fill in Architecture Overview with brief description of folder structure
- Add Domain Terminology if you spot project-specific terms
- **Keep it under 80 lines of actual content.** Be concise.

### Step 3: Create Subdirectory CLAUDE.md Files

For each major directory (3-5 max), create a CLAUDE.md using the template at `.claude/templates/folder-claude-md.md`. Typical candidates:

- `src/` or `app/` — main source folder
- `src/api/` or `src/routes/` — API layer
- `src/models/` or `src/db/` — data layer
- `src/services/` — business logic
- `tests/` — test conventions

Rules for these files:
- **Under 50 lines each.** Extremely concise.
- **Describe patterns, not file paths.** Paths go stale. Patterns persist.
- **Only create for folders that have distinct patterns worth documenting.**
- **Don't create for simple utility folders** that need no explanation.

### Step 4: Initialize Progress Tracking

Verify `.claude/specs/progress.md` exists. If not, create it from the template. If it already has content, don't overwrite.

### Step 5: Verify Test Setup

Run the test command once to verify tests can execute. If no test framework exists:
1. Recommend one appropriate for the stack
2. Ask the user if you should install and configure it
3. If yes, set it up with a sample passing test
4. Testing is **non-negotiable** for SDD — the self-healing loop depends on it

### Step 6: Report to User

```
SDD initialized. Here's what I set up:

Tech Stack: [detected]
Test Runner: [detected] (command: [command])
Architecture: [brief description]

Context files created:
- CLAUDE.md (root) — [X lines]
- src/api/CLAUDE.md — [X lines]
- src/models/CLAUDE.md — [X lines]
- [etc.]

Progress tracking: .claude/specs/progress.md

Commands:
- /spec-create [description] — Define a new feature
- /spec-implement [slug] — Build from an approved spec
- /spec-review [slug] — Audit implementation against spec

Tip: As you work, add CLAUDE.md files to new directories
when you notice the AI needs context about that area.
Use the template at .claude/templates/folder-claude-md.md.

Optional: Install recommended community skills for richer agent capabilities:
  .claude/scripts/install-skills.sh
See .claude/docs/recommended-skills.md for the full list.

Optional: Set up autonomous permissions (no more pressing 'yes' 50 times):
  .claude/scripts/set-permissions.sh autonomous
```

### Step 7: Set Up .gitattributes for Clean PRs

Check if `.gitattributes` exists. If it does, append the SDD rules. If not, create it from the kit's template. This ensures:
- Spec files, progress.md, and skill definitions are **collapsed by default** in GitHub PR diffs
- Subdirectory CLAUDE.md files are marked as documentation
- Reviewers see actual code changes first, not 2000 lines of markdown
- Files are still expandable — nothing is hidden, just de-prioritized

The key lines to add:

```
.claude/specs/** linguist-generated=true
.claude/skills/** linguist-generated=true
.claude/templates/** linguist-generated=true
**/CLAUDE.md linguist-documentation
CLAUDE.md linguist-documentation
```

### Step 8: Commit

```bash
git add .claude/ CLAUDE.md .gitattributes
# Also add any subdirectory CLAUDE.md files
git add */CLAUDE.md **/CLAUDE.md 2>/dev/null || true
git commit -m "chore: initialize spec-driven development"
```

## Important Notes

- The root CLAUDE.md loads into EVERY session. Every line costs context. Keep it lean.
- Subdirectory CLAUDE.md files only load when Claude is working in that directory. They can be more specific.
- progress.md is the state persistence mechanism. It's what makes implementation resumable across sessions.
- If the project already has a CLAUDE.md, MERGE your additions — don't replace existing content.
