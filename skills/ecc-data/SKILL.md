---
name: ecc-data
description: Load data ECC tools for datasets, cleaning, transforms, and structured data work.
---

# ECC Data

Use automatically when a task needs datasets, CSV or JSON handling, tabular analysis, cleaning, transforms, or structured data processing.

## Workflow

1. Call `load_skill_tools("ecc/data")`.
2. Use the loaded tools only when they are relevant to the current task.
3. Keep work scoped to the active thread.

## Tools

- `dataset_manager`
- `data_clean`
- `data_transform`

## Error Handling

If loading fails, respond with:

```text
Failed operation: load_skill_tools("ecc/data")
Reason: <tool error>
Recovery steps:
- Run `/help-agent101` to confirm ECC categories are available.
- Check that server/tools/ecc/data.py imports correctly.
```
