# Recommended Skills for SDD

Skills are installed at the **user level** (`~/.claude/skills/`) so they're available across all projects without bloating any single repo. The agents use them automatically when relevant.

Run the install script: `.claude/scripts/install-skills.sh`

Or install manually via the Claude Code plugin marketplace:
```
/plugin marketplace add <repo>
```

---

## Bundled with SDD Kit (project-level)

These live in this repo's `.claude/skills/` and are SDD-specific:

| Skill | Purpose |
|---|---|
| spec-create | Interactive feature spec conversation |
| spec-implement | Self-healing implementation from specs |
| spec-review | Audit implementation against spec |
| spec-init | Bootstrap SDD in a project |

---

## Recommended Install (user-level)

These complement the SDD workflow and are used by the agents during implementation.

### Anthropic Official

| Skill | Why it helps SDD | Install |
|---|---|---|
| **frontend-design** | Agents produce better UI code when implementing frontend stories | `anthropics/skills` |
| **mcp-builder** | Agents can build MCP integrations when specs require external service connections | `anthropics/skills` |
| **skill-creator** | Improve existing skills or create new ones as your workflow evolves | `anthropics/skills` |
| **web-artifacts-builder** | Build interactive HTML artifacts with React/Tailwind | `anthropics/skills` |

### Community (High Value)

| Skill | Why it helps SDD | Install |
|---|---|---|
| **superpowers** (obra) | 20+ battle-tested skills: TDD, debugging, planning, brainstorming. The `/write-plan` and `/execute-plan` commands pair well with SDD. | `obra/superpowers` |
| **vibesec** | Security-first coding. Prevents common vulnerabilities (IDOR, XSS, SQL injection) during implementation. | `BehiSecc/vibesec` |
| **systematic-debugging** | Structured debugging approach. Helps the self-healing loop fix issues methodically instead of randomly. | Search awesome-claude-skills |
| **test-driven-development** | Enforces RED-GREEN-REFACTOR cycle. Reinforces SDD's testing requirements. | Search awesome-claude-skills |
| **software-architecture** | Clean Architecture, SOLID principles, design patterns. Helps agents make better architectural decisions. | Search awesome-claude-skills |
| **planning-with-files** | Manus-style persistent markdown planning. Similar to progress.md but more structured. | Search awesome-claude-skills |
| **defense-in-depth** | Multi-layered testing and security best practices. | Search awesome-claude-skills |

### Optional (Domain-Specific)

| Skill | When to install |
|---|---|
| **aws-skills** | If your project deploys to AWS |
| **playwright-browser-automation** | If your specs require E2E browser testing |
| **d3-visualization** | If your project involves data visualization |
| **ios-simulator** | If building iOS apps |

---

## Finding More Skills

The ecosystem has 24,000+ skills. Good starting points:

- **Anthropic official:** https://github.com/anthropics/skills
- **VoltAgent collection:** https://github.com/VoltAgent/awesome-agent-skills (500+ curated, includes official dev team skills from Vercel, Stripe, Cloudflare, etc.)
- **Superpowers:** https://github.com/obra/superpowers (27k+ stars, most popular collection)
- **Awesome Claude Skills:** https://github.com/travisvn/awesome-claude-skills
- **Awesome Claude Code:** https://github.com/jqueryscript/awesome-claude-code

---

## How Skills Interact with SDD

The SDD skills (spec-create, spec-implement, etc.) are the **workflow**. The recommended skills above are the **toolbox** the agents draw from during implementation.

For example, when `/spec-implement` delegates a story to a subagent:
- If the story involves building a UI → the agent may use **frontend-design**
- If it encounters a bug → it may use **systematic-debugging**
- If it's writing tests → it may follow **test-driven-development** patterns
- If it's handling user input → **vibesec** helps prevent injection vulnerabilities

You don't need to tell the agent which skills to use. If the skill descriptions match the task, the agent loads them automatically.
