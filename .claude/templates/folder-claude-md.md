# Folder Context Template

> Copy this file into any major subdirectory as `CLAUDE.md` and customize it.
> Keep each file under 150 lines. Claude Code loads these automatically when working in the directory.
> Describe capabilities and patterns, NOT specific file paths (they go stale).

## Purpose

[What does this folder contain? What responsibility does it own?]

## Patterns

[What patterns are used here? How are things structured?]
[Example: "Every API endpoint follows the controller → service → repository pattern."]
[Example: "All models extend BaseModel and use soft deletes."]

## Testing

[How are things in this folder tested? Where do the tests live?]
[Example: "Each service has a corresponding test file in __tests__/ using the naming pattern service-name.test.ts"]

## Dependencies

[What does this folder depend on? What depends on it?]

## Gotchas

[Common mistakes or non-obvious things about this area of the code.]
[Example: "The auth middleware must be applied BEFORE the rate limiter."]
[Example: "Don't import from /internal — use the public API from index.ts."]
