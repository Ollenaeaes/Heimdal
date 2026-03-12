# Feature Spec: [Feature Name]

**Slug:** `[feature-slug]`
**Created:** [date]
**Status:** draft | approved | in-progress | completed
**Priority:** critical | high | medium | low

---

## Overview

[2-3 sentence description of what this feature does and why it matters]

## Problem Statement

[What problem does this solve? What's the current pain point?]

## Out of Scope

[Explicitly list what this feature does NOT include. This is critical — it prevents scope creep and tells the AI what NOT to build.]

- NOT: [thing 1]
- NOT: [thing 2]

---

## User Stories

### Story 1: [Title]

**As a** [role]
**I want to** [action]
**So that** [benefit]

**Acceptance Criteria:**

- GIVEN [precondition] WHEN [action] THEN [expected result]
- GIVEN [precondition] WHEN [action] THEN [expected result]

**Test Requirements:**

- [ ] Test: [describe what the test verifies — must test real behavior]
- [ ] Test: [describe edge case test]

**Technical Notes:**

[Any implementation hints, constraints, or patterns to follow]

---

### Story 2: [Title]

**As a** [role]
**I want to** [action]
**So that** [benefit]

**Acceptance Criteria:**

- GIVEN [precondition] WHEN [action] THEN [expected result]

**Test Requirements:**

- [ ] Test: [describe what the test verifies]

**Technical Notes:**

[Any implementation hints]

---

## Technical Design

### Data Model Changes

[Describe any new models, schema changes, or data structures]

### API Changes

[Describe any new endpoints, changed endpoints, or API contracts]

### Dependencies

[External services, libraries, or other features this depends on]

### Security Considerations

[Authentication, authorization, input validation, data exposure risks]

---

## Implementation Order

[Group stories by what can run in parallel. Stories in the same group must NOT touch the same files or depend on each other. Stories in later groups depend on earlier groups completing.]

### Group 1 (parallel — no dependencies)
- Story X — [brief scope: what files/area it touches]
- Story Y — [brief scope: different files/area]

### Group 2 (parallel — after Group 1)
- Story Z — depends on Story X, [scope]
- Story W — depends on Story Y, [scope]

### Group 3 (sequential — after Group 2)
- Story V — depends on Z and W, [scope]

**Parallel safety rules:**
- Stories in the same group must touch DIFFERENT files/folders
- If two stories might edit the same file, they go in different groups
- Database migrations must be sequential (never parallel)
- Shared utilities/helpers: the story that creates them goes first

---

## Development Approach

[The agent fills this in. The human doesn't need to write this section.]

### Simplifications (what starts simple)

[List what will be implemented as the simplest working version. Example:
- Authentication: email/password login, no OAuth yet
- Data access: application-level filtering, not database-level RLS yet
- Email notifications: logged to console in dev, real email service later]

### Upgrade Path (what changes for production)

[List what would need a future story to upgrade. Example:
- "Add OAuth/SSO login" would be a separate story
- "Move data access rules to Postgres RLS" would be a separate story
- "Integrate SendGrid for real email delivery" would be a separate story]

### Architecture Decisions

[Technical choices the agent made and why. Written for the agent's future reference and for senior developer review. Example:
- Chose session-based auth over JWT because the app is server-rendered
- Used a service layer between routes and database to keep upgrade paths clean]

---

## Verification Checklist

Before this feature is marked complete:

- [ ] All user stories implemented
- [ ] All acceptance criteria met
- [ ] All tests written and passing
- [ ] Tests verify real behavior (not just status codes)
- [ ] Edge cases handled
- [ ] No regressions in existing tests
- [ ] Code committed with proper messages
- [ ] Ready for human review
