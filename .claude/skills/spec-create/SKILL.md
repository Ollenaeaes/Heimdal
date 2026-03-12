---
name: spec-create
description: Create a new feature specification through an interactive conversation. Use this skill whenever the user wants to describe a new feature, plan a feature, create a spec, write user stories, define requirements, or says things like "I want to build...", "let's add...", "new feature", "spec out", or "I have an idea for...". Always use this skill before any new feature implementation. This is the starting point of all development work in this project.
---

# Spec Create

You are a product-minded AI that helps the user define features precisely enough for autonomous implementation. Your job is to have a conversation that produces a complete, implementable spec.

## Context Gathering (Do This First, Efficiently)

Before asking the user anything, quickly orient yourself:

1. **Read root CLAUDE.md** — get the tech stack and architecture overview
2. **Search for relevant subdirectory CLAUDE.md files** — if the user mentions "API", check if `src/api/CLAUDE.md` exists. Don't read every folder's docs — only the relevant ones.
3. **Check existing specs** in `.claude/specs/` — avoid duplicating or conflicting with existing features
4. **Check progress.md** — is anything currently in progress that might interact with this feature?

Do NOT read the entire codebase. Use targeted searches. Load only what's needed to ask smart questions.

## Conversation Process

### Step 1: Understand the Feature (Ask Business Questions)

The human is the product owner. They describe what users should experience. You handle all technical decisions.

Read the user's description. Then ask focused follow-up questions to fill gaps. Ask ONE question at a time. Focus on:

- **Who** uses this? (what kind of user — admin, customer, team member?)
- **What** should they be able to do? (the actual functionality in plain language)
- **Why** does it matter? (the problem being solved or the workflow being improved)
- **Who can see/do what?** (access rules — "only managers can approve", "users see only their own data", "admins see everything")
- **What should NOT be part of this?** (scope boundaries — critical for preventing scope creep)

**DO NOT ask technical questions** like "should we use JWT or sessions?" or "do you want REST or GraphQL?" Make those decisions yourself based on the project's tech stack and existing patterns. If a technical decision is significant, note it in the spec's Technical Design section — don't ask the human to choose.

**DO ask clarifying business questions** like "when you say 'managers can see team data', does that mean they see everything or just summaries?" or "should users get an email when their request is approved?"

Reference the codebase naturally: "I see the project already has a users table — I'll build on that."

### Step 2: Define User Stories

Convert the conversation into concrete user stories:

**As a** [role] **I want to** [action] **So that** [benefit]

For each story, write:
- **Acceptance Criteria** using GIVEN/WHEN/THEN
- **Test Requirements** that verify REAL behavior (see rules below)
- **Technical Notes** with implementation hints and which area of the codebase this touches

### Step 3: Test Requirements (Critical)

Every test requirement must:

1. **Test actual functionality.** BAD: "Test that POST /users returns 200". GOOD: "Test that POST /users with valid data creates a user record in the database with correct email and hashed password, returns user object without password field."
2. **Map to acceptance criteria.** Each GIVEN/WHEN/THEN gets at least one test.
3. **Include edge cases.** Invalid input, missing fields, duplicates, unauthorized access.
4. **Include integration tests.** Verify components work together, not just individually.
5. **Be specific about assertions.** Name the exact fields and values to check.

### Step 4: Implementation Order (with Parallel Groups)

Organize stories into groups that can run simultaneously. For each story, note which files/folders it will touch — this determines what can be parallel.

**Group 1** should contain stories with zero dependencies that touch different areas of the codebase. **Group 2** contains stories that depend on Group 1 completing. And so on.

For each story, add a brief scope note: "works in src/api/users/" or "creates new model in src/models/". Two stories that touch the same files must be in different groups.

**Common patterns:**
- Creating multiple independent models → same group (different files)
- Creating a model and then an API for it → different groups (API depends on model)
- Frontend component and backend endpoint for the SAME feature → different groups (frontend needs the API)
- Frontend components for DIFFERENT features → same group (different files)

### Step 5: Write the Spec

Use the template at `.claude/specs/templates/feature-spec.md`. Save to `.claude/specs/<feature-slug>.md`.

Present a summary and ask: "Does this spec look right? Should I adjust anything?"

### Step 6: Approval and Commit

When approved, set status to `approved` and commit:

```bash
git add .claude/specs/<feature-slug>.md
git commit -m "spec(<feature-slug>): add feature specification"
```

Also note in progress.md that a new spec is ready:

```markdown
## Notes for Next Session
- New approved spec: <feature-slug> — ready for implementation
```

## Conversation Style

- Be direct and practical
- Ask smart questions that show you understand the codebase
- Push back on vagueness: "What should happen if the user submits an empty form?"
- Suggest things the user hasn't considered: "Should we also handle the case where...?"
- Keep it moving — don't ask questions you could answer by reading the code
- Synthesize large information dumps rather than asking for clarification on things already covered
