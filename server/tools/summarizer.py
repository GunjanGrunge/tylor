"""
server/tools/summarizer.py — async thread summarization via Bedrock Opus.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import boto3

logger = logging.getLogger(__name__)

DEFAULT_LAST_N_MESSAGES = 20
DEFAULT_SUMMARY_MAX_TOKENS = 1024
DEFAULT_BEDROCK_OPUS_MODEL = "us.anthropic.claude-opus-4-7-20251101-v1:0"


def _message_text(message: dict) -> str:
    role = message.get("Role") or message.get("role") or "unknown"
    content = message.get("Content") or message.get("content") or ""
    return f"{role}: {content}"


def _last_messages(db: Any, thread_id: str, limit: int = DEFAULT_LAST_N_MESSAGES) -> list[dict]:
    messages = db.query_thread(thread_id, f"THREAD#{thread_id}#MSG#")
    messages.sort(key=lambda item: item.get("SK", ""))
    return messages[-limit:]


def _raw_fallback_summary(messages: list[dict]) -> str:
    if not messages:
        return "No messages were available for fallback summary."
    return "\n".join(_message_text(message) for message in messages)


def _extract_bedrock_text(response: dict) -> str:
    body = response.get("body")
    payload = body.read() if hasattr(body, "read") else body
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    data = json.loads(payload)

    content = data.get("content", [])
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "".join(parts).strip()
    if isinstance(content, str):
        return content.strip()
    return ""


def _summary_prompt(messages: list[dict]) -> str:
    transcript = _raw_fallback_summary(messages)
    return (
        "Summarize this development thread for future context restoration. "
        "Keep durable decisions, changed files, unresolved risks, and next steps.\n\n"
        f"{transcript}"
    )


def _build_bedrock_client() -> Any:
    from server.config import config

    session_kwargs: dict[str, str] = {}
    if config.get("aws_profile"):
        session_kwargs["profile_name"] = config["aws_profile"]
    session = boto3.Session(**session_kwargs)
    return session.client(
        "bedrock-runtime",
        region_name=config.get("bedrock_region", "us-east-1"),
    )


def _bedrock_model_id() -> str:
    from server.config import config

    return config.get("bedrock_opus_model") or DEFAULT_BEDROCK_OPUS_MODEL


def _mark_thread_killed(db: Any, thread_id: str) -> None:
    meta = db.get_thread_meta(thread_id)
    if not meta:
        return  # thread was deleted; don't create a ghost META item
    attributes = dict(meta)
    attributes["Status"] = "killed"
    db.put_item(f"THREAD#{thread_id}#META", attributes)


def _write_summary(
    db: Any,
    thread_id: str,
    summary: str,
    summary_type: str,
    error: str | None = None,
) -> None:
    attributes = {
        "Summary": summary,
        "SummaryType": summary_type,
    }
    if error:
        attributes["Error"] = error
    db.put_item(f"THREAD#{thread_id}#SUMMARY", attributes)


def _log_failure(db: Any, thread_id: str, error: str) -> None:
    from server.tools.tylor import _now_iso

    sk = f"THREAD#{thread_id}#MSG#{_now_iso()}#SUMMARY_FAILURE"
    db.put_item(sk, {
        "Role": "system",
        "Content": f"kill_thread summarization failed: {error}",
    })


async def summarize_thread(
    thread_id: str,
    db: Any,
    bedrock_client: Any | None = None,
    model_id: str | None = None,
    last_n: int = DEFAULT_LAST_N_MESSAGES,
) -> None:
    """
    Summarize a thread, persist the result, and mark the thread killed.
    On Bedrock failure, stores raw last-N messages and logs the failure.
    """
    messages = _last_messages(db, thread_id, last_n)
    bedrock = bedrock_client or _build_bedrock_client()
    model = model_id or _bedrock_model_id()

    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": DEFAULT_SUMMARY_MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": _summary_prompt(messages),
                }
            ],
        }
        response = await asyncio.to_thread(
            bedrock.invoke_model,
            modelId=model,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        summary = _extract_bedrock_text(response)
        if not summary:
            raise RuntimeError("Bedrock returned an empty summary")
        _write_summary(db, thread_id, summary, "bedrock_opus")
    except Exception as exc:
        error = str(exc)
        logger.exception("Thread summarization failed for %s", thread_id)
        _write_summary(
            db,
            thread_id,
            _raw_fallback_summary(messages),
            "raw_fallback",
            error=error,
        )
        _log_failure(db, thread_id, error)
    finally:
        _mark_thread_killed(db, thread_id)
