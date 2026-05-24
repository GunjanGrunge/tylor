---
name: ecc-diagrams
description: Load diagram ECC tools for flowcharts, architecture visuals, and process maps.
---

# ECC Diagrams

Use automatically when a task needs diagrams, flowcharts, architecture visuals, process maps, graph-like explanations, or sequence-style visual planning.

## Workflow

1. Call `load_skill_tools("ecc/diagrams")`.
2. Use the loaded tools only when they are relevant to the current task.
3. Keep work scoped to the active thread.

## Tools

- `diagram_gen`
- `flowchart_gen`

## Error Handling

If loading fails, respond with:

```text
Failed operation: load_skill_tools("ecc/diagrams")
Reason: <tool error>
Recovery steps:
- Run `/help-agent101` to confirm ECC categories are available.
- Check that server/tools/ecc/diagrams.py imports correctly.
```
