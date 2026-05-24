---
name: ecc-presentation
description: Load presentation ECC tools for slide decks, documents, reports, and polished deliverables.
---

# ECC Presentation

Use automatically when a task needs presentations, slide decks, PPTX output, documents, reports, or polished written deliverables.

## Workflow

1. Call `load_skill_tools("ecc/presentation")`.
2. Use the loaded tools only when they are relevant to the current task.
3. Keep work scoped to the active thread.

## Tools

- `build_pptx`
- `build_doc`

## Error Handling

If loading fails, respond with:

```text
Failed operation: load_skill_tools("ecc/presentation")
Reason: <tool error>
Recovery steps:
- Run `/help-agent101` to confirm ECC categories are available.
- Check that server/tools/ecc/presentation.py imports correctly.
```
