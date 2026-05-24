---
name: ecc-web
description: Load web research ECC tools for fetching pages, scraping public content, and source collection.
---

# ECC Web

Use automatically when a task needs web research, page fetching, public content scraping, source collection, URLs, or website inspection.

## Workflow

1. Call `load_skill_tools("ecc/web")`.
2. Use the loaded tools only when they are relevant to the current task.
3. Keep work scoped to the active thread.

## Tools

- `web_fetch`
- `web_scrape`

## Error Handling

If loading fails, respond with:

```text
Failed operation: load_skill_tools("ecc/web")
Reason: <tool error>
Recovery steps:
- Run `/help-agent101` to confirm ECC categories are available.
- Check that server/tools/ecc/web.py imports correctly.
```
