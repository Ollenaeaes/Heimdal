# SDD Kit — Spec-Driven Development for AI Coding

A drop-in toolkit that brings structured, spec-driven development to any repository. Built for Claude Code (terminal, web, mobile). Produces specs compatible with any AI coding tool.

## The Problem

Vibe coding breaks down on real projects because:
- The AI doesn't know what "done" looks like
- Tests check status codes, not actual behavior
- Context window fills up and the AI loses track
- No state persists between sessions
- Scope creep happens silently

## What This Does

SDD Kit gives you a structured workflow with context management built in:

1. **You describe what you want** → AI asks smart questions, understands your codebase
2. **Together you produce a spec** → User stories, acceptance criteria, real test requirements
3. **AI implements autonomously** → Story by story, using subagents for context isolation, self-healing until tests pass
4. **State persists across sessions** → progress.md tracks everything so you can stop and resume anytime

## Quick Start

```bash
# Copy the kit into your project root
cp -r sdd-kit/.claude your-project/
cp sdd-kit/CLAUDE.md your-project/
cp sdd-kit/.gitattributes your-project/

# Open Claude Code in your project
cd your-project

# Initialize SDD for your specific project
/spec-init

# Optional: stop pressing 'yes' 50 times per story
# (auto-approves edits/tests/git, blocks rm -rf/sudo/push)
.claude/scripts/set-permissions.sh autonomous

# Start defining your first feature
/spec-create "user authentication with email and password"
```

## Commands

| Command | What it does |
|---|---|
| `/spec-init` | Analyze your project and set up SDD (run once) |
| `/spec-create` | Interactive conversation → structured spec |
| `/spec-implement` | Autonomous implementation with self-healing |
| `/spec-review` | Audit implementation against spec |
| `/learn-from-review` | Process review feedback into LESSONS.md |

## Context Management

This is what makes the kit work on real projects without blowing up the context window.

### Hierarchical CLAUDE.md Files

The root `CLAUDE.md` stays slim (under 80 lines of content). It loads into every session, so every line costs context. Deeper documentation lives in subdirectory CLAUDE.md files:

```
project/
├── CLAUDE.md                    # Slim: methodology, commands, tech stack
├── src/
│   ├── api/
│   │   └── CLAUDE.md           # API patterns, endpoint conventions
│   ├── models/
│   │   └── CLAUDE.md           # Data model patterns, validation rules
│   └── services/
│       └── CLAUDE.md           # Business logic patterns
└── tests/
    └── CLAUDE.md               # Test conventions, fixture patterns
```

Claude Code loads subdirectory files only when working in that directory. This keeps the context focused.

### Progress Tracking (progress.md)

The `.claude/specs/progress.md` file is the state persistence mechanism. The implementation skill:
- Reads it at the start of every session
- Updates it after every completed story
- Records decisions, issues, and notes for the next session

This means you can stop mid-feature, close your laptop, come back next week, and `/spec-implement` picks up exactly where it left off.

### Subagent Delegation

Each user story is implemented by a subagent with a focused context:
- The orchestrator gives the subagent ONLY the current story's details and relevant files
- The subagent implements, tests, and self-heals in its own context window
- Results come back clean — the orchestrator's context isn't polluted with debug output
- After each story, the orchestrator compacts and updates progress.md

### Just-in-Time File Loading

The skills never read the entire codebase upfront. Instead:
- Search for relevant files based on the current story
- Read only the 2-5 files needed for the task at hand
- Reference subdirectory CLAUDE.md for patterns, not specific file paths (paths go stale)

## The Self-Healing Loop

Stories are organized into **parallel groups** in each spec. Stories within a group touch different files and can run simultaneously. Groups run sequentially because later groups depend on earlier ones.

**Sequential mode** (default):
```
For each group:
  For each story:
    1. Subagent implements the code
    2. Subagent writes tests that verify REAL behavior
    3. Run tests → if fail → fix → rerun (max 5 attempts)
    4. Run full suite for regressions
    5. Commit
  Next story
Next group
```

**Parallel mode** (say "run in parallel" or "build fast"):
```
For each group:
  Launch all stories as simultaneous subagents:
    Each subagent: implement → test → self-heal → report done
  Orchestrator verifies all, runs full suite, commits each
Next group
```

You can see which stories can run in parallel by looking at the spec's Implementation Order section — it shows the groups and what files each story touches.

## Test Quality Rules

The kit enforces strict testing:
- Every acceptance criterion gets a test
- Tests verify actual data, state changes, and side effects
- Tests cover error and edge cases
- Tests are never weakened to make them pass
- No story is "done" until its tests pass

## Project Structure

```
your-project/
├── .gitattributes                         # Collapses SDD markdown in PR diffs
├── CLAUDE.md                              # Slim project config (<80 lines)
├── .claude/
│   ├── LESSONS.md                        # Compound learning from reviews
│   ├── skills/
│   │   ├── spec-create/SKILL.md          # Feature spec conversation
│   │   ├── spec-implement/SKILL.md       # Self-healing implementation
│   │   ├── spec-review/SKILL.md          # Implementation audit
│   │   ├── spec-init/SKILL.md            # Project bootstrapping
│   │   └── learn-from-review/SKILL.md    # Review → lessons pipeline
│   ├── specs/
│   │   ├── templates/
│   │   │   └── feature-spec.md           # Spec template
│   │   ├── progress.md                   # State persistence scratchpad
│   │   └── completed/                    # Archive for done specs
│   ├── configs/
│   │   ├── settings-autonomous.json      # Auto-approve safe ops
│   │   └── settings-yolo.json            # Bypass all (containers only)
│   ├── docs/
│   │   └── recommended-skills.md         # Curated skills reference
│   ├── scripts/
│   │   ├── install-skills.sh             # Community skill installer
│   │   └── set-permissions.sh            # Apply permission profiles
│   └── templates/
│       └── folder-claude-md.md           # Template for subdirectory docs
├── src/
│   ├── api/
│   │   └── CLAUDE.md                     # API-specific patterns
│   └── models/
│       └── CLAUDE.md                     # Data model patterns
```

## Learning From Reviews (LESSONS.md)

The kit includes a compound learning mechanism. Every code review — whether from a human teammate, Claude Code Review on GitHub, or the local `/code-review` plugin — can feed back into `.claude/LESSONS.md`.

This file is read at the start of every session. Over time, the agent stops repeating mistakes and learns project-specific patterns that no general model training could provide.

**How it works:**

1. A reviewer (human or AI) finds an issue in your PR
2. You run `/learn-from-review` (or say "learn from the PR review")
3. The agent reads the review comments, extracts real lessons, and adds them to LESSONS.md
4. Next session, the agent reads LESSONS.md and doesn't make those mistakes again

**Setting up Claude Code Review on GitHub (optional but recommended):**

The easiest option — Anthropic's managed Code Review (Team/Enterprise plans):
1. Go to your Claude Code settings
2. Enable Code Review
3. Install the GitHub App
4. Select your repositories
5. Reviews run automatically on every new PR — no config needed

The free option — the open-source code-review plugin:
```bash
# Install the plugin
/plugin install code-review

# Run locally before pushing
/code-review

# Or post as PR comment
/code-review --comment
```

The free GitHub Action (runs in your CI):
1. Add `ANTHROPIC_API_KEY` to your repo's GitHub secrets
2. Run `/install-github-app` in Claude Code
3. Reviews run automatically via GitHub Actions

**Feeding review findings into LESSONS.md:**

After a review, tell Claude Code:
```
# After a human review
"The reviewer said we should always validate email format — add that to lessons"

# After GitHub Code Review
"Learn from the PR review comments"
# (The agent reads comments via `gh pr view --comments`)

# After local /code-review
"Update lessons from that review"
```

The `/learn-from-review` skill handles the rest — it reads the feedback, filters out noise, and adds specific actionable lessons.

## Permission Modes (Stop Pressing Yes)

By default Claude Code asks permission for every action. During SDD implementation, that means approving 50+ prompts per story. The kit includes three permission profiles:

```bash
# Recommended: auto-approves edits, tests, git, common commands
# Blocks: rm -rf, sudo, git push, pipe-to-bash
.claude/scripts/set-permissions.sh autonomous

# Nuclear: bypasses ALL permissions (containers/VMs only!)
.claude/scripts/set-permissions.sh yolo

# Back to default
.claude/scripts/set-permissions.sh reset
```

The **autonomous** profile is designed for SDD. The agent can edit files, run tests, commit code, and self-heal without interruption. But it can't `rm -rf` your project, `sudo` anything, or `git push` — you push when you're satisfied with the work.

You can also use **Shift+Tab** inside Claude Code to cycle through modes interactively: normal → accept-edits → plan-mode.

## Agent Skills Ecosystem

The SDD skills (spec-create, spec-implement, etc.) are the **workflow**. But during implementation, agents can draw from a much larger toolbox of community skills for frontend design, security, debugging, TDD, and more.

These are installed at the user level (`~/.claude/skills/`) so they're available across all your projects:

```bash
# One-time setup — installs 5 recommended skills
chmod +x .claude/scripts/install-skills.sh
.claude/scripts/install-skills.sh
```

What gets installed:
- **Frontend Design** (Anthropic) — better UI/UX implementation
- **MCP Builder** (Anthropic) — build external service integrations
- **Skill Creator** (Anthropic) — improve or create new skills
- **Superpowers** (obra, 27k+ stars) — TDD, debugging, planning, and 20+ more
- **VibeSec** — prevents common security vulnerabilities during coding

Agents use these automatically when relevant. If a story involves building a UI, the agent loads the frontend-design skill. If it encounters a bug, it may use systematic-debugging. You don't need to tell it which skills to use.

See `.claude/docs/recommended-skills.md` for the full list and additional optional skills.

## Clean PRs for Human Reviewers

SDD generates a lot of markdown — specs, progress tracking, context files. Without handling this, a PR that adds 50 lines of code might show as 2000+ lines changed. The kit includes a `.gitattributes` file that solves this using GitHub's Linguist:

- **Spec files, skills, and templates** are marked `linguist-generated` — collapsed by default in PR diffs
- **CLAUDE.md files** are marked `linguist-documentation` — excluded from language stats, collapsed in diffs
- **Nothing is hidden.** Reviewers can expand any file with one click. The markdown is still there, just de-prioritized so code changes come first.

A senior developer reviewing a PR will see the actual code and tests at the top, with all the SDD markdown collapsed below. They can skip it entirely or expand individual files if they want to check the spec.

This also keeps your repo's language stats accurate — GitHub won't report your project as "90% Markdown."

## Customizing

After `/spec-init`, you can:
- Edit `CLAUDE.md` to refine commands and architecture description
- Add CLAUDE.md files to new directories using `.claude/templates/folder-claude-md.md`
- Modify the spec template to fit your team's preferences
- Adjust skill instructions if your workflow differs

## Philosophy

- **Specs are the source of truth.** Code is derived from specs.
- **Tests prove functionality.** Real behavior, not just "it runs."
- **Context is precious.** Load only what's needed, when it's needed.
- **State persists in files.** progress.md survives sessions, compactions, and breaks.
- **Self-healing over hand-holding.** Fix your own mistakes before asking.
- **Small increments.** One story at a time. Verify. Commit. Move on.
- **Out of scope matters.** What NOT to build prevents scope creep.
