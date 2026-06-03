# Plans

## How to Write a Plan

### Filename Format
```
YYYY-MM-DD_plan-name.md
```
Example: `2026-04-29_refactor-auth.md`

### Structure
1. **Title**: Brief description
2. **Why**: Motivation behind the plan
3. **Checklist**: Steps with `[ ]` for pending, `[x]` for done

### Rules
- Always include checklists
- Mark steps done immediately after completion
- Update plan when scope changes

### Example
```markdown
# 2026-04-29 Fix Login Bug

## Why
Users stuck on login. Auth token expiry check broken.

## Checklist
- [x] Identify root cause
- [ ] Fix token expiry logic
- [ ] Test locally
- [ ] Deploy
```
