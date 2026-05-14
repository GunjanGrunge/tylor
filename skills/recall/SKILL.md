---
name: recall
description: Recall relevant agent101 memory facts by asking for a thread ID and query, then calling recall_memory.
---

# /recall

Use when the user invokes `/recall` or asks to search a thread's memory.

## Workflow

1. Ask for the thread ID if it was not provided.
2. Ask for the recall query if it was not provided.
3. Call `recall_memory(thread_id: str, query: str)`.
4. Show a formatted confirmation and results:

```text
Recall results for thread: <thread_id>
Query: <query>
results:
- <fact or memory content>
```

5. If results are empty, say no matching memory was found.

## Error Handling

Use this recovery format exactly.

If the tool fails, respond with:

```text
Failed operation: recall_memory
Reason: <tool error>
Recovery steps:
- Verify the thread ID with /list-threads.
- Use a non-empty query.
- Check OPENSEARCH_HOST and Bedrock embedding configuration if semantic recall is unavailable.
```
