"""
server/storage/dynamo.py — DynamoDB storage client for agent101.

Single-table design. All items MUST include:
  PK, SK, CreatedAt (ISO 8601 UTC), UpdatedAt (ISO 8601 UTC), Version (int)

Key schema:
  PK: USER#{user_id}    SK: THREAD#{thread_id}#META
  PK: USER#{user_id}    SK: THREAD#{thread_id}#MSG#{ts}
  PK: USER#{user_id}    SK: THREAD#{thread_id}#BLOB#{key}
  PK: USER#{user_id}    SK: MEMORY#{memory_id}

Thread isolation: all SK operations are validated to contain THREAD#{thread_id}.
Size limit: items >400KB are rejected — use s3.py for large content.
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from boto3.dynamodb.types import TypeSerializer
from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)

ITEM_SIZE_LIMIT = 400 * 1024  # 400 KB
_AGENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serialised_size(item: dict) -> int:
    """Approximate DynamoDB item size using JSON serialisation."""
    return len(json.dumps(item, default=str).encode("utf-8"))


def _unique_event_suffix() -> str:
    return f"{_now_iso()}#{uuid.uuid4().hex}"


class DynamoClient:
    """
    Typed DynamoDB client enforcing single-table schema, mandatory base fields,
    item size limit, and thread-isolation on all operations.
    """

    ITEM_SIZE_LIMIT = ITEM_SIZE_LIMIT

    CURRENT_THREAD_SK = "THREAD#CURRENT#META"

    def __init__(
        self,
        table_name: str,
        user_id: str = "default",
        profile: str | None = None,
    ) -> None:
        self.table_name = table_name
        self.user_id = user_id

        session_kwargs: dict = {}
        if profile:
            session_kwargs["profile_name"] = profile

        session = boto3.Session(**session_kwargs)
        resource = session.resource("dynamodb")
        self.table = resource.Table(table_name)
        self._client = session.client("dynamodb")
        self._serializer = TypeSerializer()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pk(self) -> str:
        return f"USER#{self.user_id}"

    def _assert_thread_isolation(self, thread_id: str, sk: str) -> None:
        """Raise ToolError if SK does not belong to this thread."""
        thread_prefix = f"THREAD#{thread_id}#"
        if not sk.startswith(thread_prefix):
            raise ToolError(
                f"Thread isolation violation: SK '{sk}' does not belong to thread '{thread_id}'"
            )

    def _inject_base_fields(self, item: dict, existing_version: int = 0) -> dict:
        """Add/overwrite mandatory base fields. Version increments by 1."""
        now = _now_iso()
        item.setdefault("CreatedAt", now)
        item["UpdatedAt"] = now
        item["Version"] = existing_version + 1
        return item

    def _validate_size(self, item: dict) -> None:
        size = _serialised_size(item)
        if size > self.ITEM_SIZE_LIMIT:
            raise ToolError(
                f"Item exceeds 400KB ({size // 1024}KB) — use s3.py for large content"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put_item(self, sk: str, attributes: dict) -> dict:
        """
        Write an item.
        - Injects PK, SK, CreatedAt, UpdatedAt, Version.
        - Validates item size ≤ 400KB.
        - Returns the written item dict.
        """
        # Fetch existing version for increment (if item exists)
        existing = self._raw_get(sk)
        existing_version = int(existing.get("Version", 0)) if existing else 0

        item = dict(attributes)
        item["PK"] = self._pk()
        item["SK"] = sk
        self._inject_base_fields(item, existing_version)

        # Preserve original CreatedAt if item already exists
        if existing and "CreatedAt" in existing:
            item["CreatedAt"] = existing["CreatedAt"]

        self._validate_size(item)
        self.table.put_item(Item=item)
        return item

    def get_item(self, thread_id: str, sk: str) -> dict | None:
        """
        Read a single item by (PK, SK).
        Enforces thread isolation: SK must contain THREAD#{thread_id}.
        Returns None if not found.
        """
        self._assert_thread_isolation(thread_id, sk)
        response = self.table.get_item(Key={"PK": self._pk(), "SK": sk})
        return response.get("Item")

    def query_thread(self, thread_id: str, sk_prefix: str) -> list:
        """
        Query all items for a thread by SK prefix.
        SK prefix must contain THREAD#{thread_id} for isolation.
        """
        self._assert_thread_isolation(thread_id, sk_prefix)
        response = self.table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk()) & Key("SK").begins_with(sk_prefix)
            )
        )
        return response.get("Items", [])

    def delete_item(self, thread_id: str, sk: str) -> None:
        """
        Delete an item. Enforces thread isolation.
        """
        self._assert_thread_isolation(thread_id, sk)
        self.table.delete_item(Key={"PK": self._pk(), "SK": sk})

    def _validate_agent_id(self, agent_id: str) -> None:
        if not agent_id or not _AGENT_ID_RE.match(agent_id):
            raise ToolError("Invalid agent_id")

    def put_agent_output(
        self,
        thread_id: str,
        agent_id: str,
        output: str,
        task: str | None = None,
    ) -> dict:
        """Persist completed sub-agent output under its parent thread."""
        self._validate_agent_id(agent_id)
        sk = f"THREAD#{thread_id}#AGENT#{agent_id}#OUT#{_unique_event_suffix()}"
        self._assert_thread_isolation(thread_id, sk)

        attributes = {
            "ThreadId": thread_id,
            "AgentId": agent_id,
            "Type": "agent_output",
            "Output": output,
        }
        if task is not None:
            attributes["Task"] = task
        return self.put_item(sk=sk, attributes=attributes)

    def put_agent_handoff(
        self,
        thread_id: str,
        agent_id: str,
        handoff_state: dict,
    ) -> dict:
        """Persist sub-agent handoff state as a distinct thread-scoped item."""
        self._validate_agent_id(agent_id)
        sk = f"THREAD#{thread_id}#AGENT#{agent_id}#HANDOFF#{_unique_event_suffix()}"
        self._assert_thread_isolation(thread_id, sk)
        return self.put_item(
            sk=sk,
            attributes={
                "ThreadId": thread_id,
                "AgentId": agent_id,
                "Type": "agent_handoff",
                "HandoffState": handoff_state,
            },
        )

    def put_agent_state(
        self,
        thread_id: str,
        agent_id: str,
        state: dict,
    ) -> dict:
        """Persist durable sub-agent lifecycle state under its parent thread."""
        self._validate_agent_id(agent_id)
        sk = f"THREAD#{thread_id}#AGENT#{agent_id}#STATE"
        self._assert_thread_isolation(thread_id, sk)
        attributes = {
            "ThreadId": thread_id,
            "AgentId": agent_id,
            "Type": "agent_state",
            **state,
        }
        return self.put_item(sk=sk, attributes=attributes)

    def query_agent_states(self, thread_id: str) -> list:
        """Return persisted sub-agent state records for one thread only."""
        items = self.query_thread(thread_id, f"THREAD#{thread_id}#AGENT#")
        return [item for item in items if item.get("SK", "").endswith("#STATE")]

    def get_thread_meta(self, thread_id: str) -> dict | None:
        """Return thread META item for the given thread_id."""
        return self.get_item(thread_id, f"THREAD#{thread_id}#META")

    def get_current_thread_marker(self) -> dict | None:
        """Return the current-thread marker item without isolation enforcement."""
        return self._raw_get(self.CURRENT_THREAD_SK)

    def resolve_thread_id(self, thread_id: str | None = None) -> str:
        """Resolve an explicit thread_id or the active current-thread marker."""
        if thread_id:
            return thread_id
        marker = self.get_current_thread_marker()
        if not marker or not marker.get("CurrentThreadId"):
            raise ToolError("No active thread — switch_thread or provide thread_id first")
        return marker["CurrentThreadId"]

    def set_sandbox_roots(self, thread_id: str, sandbox_roots: list[str]) -> dict:
        """Persist sandbox roots on thread metadata."""
        meta = self.get_thread_meta(thread_id)
        if not meta:
            raise ToolError(f"Thread not found: {thread_id}")
        updated = dict(meta)
        updated["sandbox_roots"] = list(sandbox_roots)
        sk = f"THREAD#{thread_id}#META"
        self._assert_thread_isolation(thread_id, sk)
        return self.put_item(sk=sk, attributes=updated)

    def query_all(self, sk_prefix: str) -> list:
        """
        Query all items with SK beginning with sk_prefix across all threads.
        No thread isolation check — used for cross-thread operations (list, name-uniqueness).
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("PK").eq(self._pk()) & Key("SK").begins_with(sk_prefix)
            )
        )
        return response.get("Items", [])

    def _serialize_item(self, item: dict) -> dict:
        return {key: self._serializer.serialize(value) for key, value in item.items()}

    def transact_write_items(self, transact_items: list[dict]) -> None:
        """Execute a DynamoDB TransactWriteItems call with serialized items."""
        try:
            self._client.transact_write_items(TransactItems=transact_items)
        except Exception as exc:
            raise ToolError(f"TransactWriteItems failed: {exc}") from exc

    def switch_thread(self, target_thread_id: str) -> dict:
        """Atomically switch the current thread marker and update thread metadata."""
        target_sk = f"THREAD#{target_thread_id}#META"
        target_meta = self._raw_get(target_sk)
        if not target_meta:
            raise ToolError(f"Thread not found: {target_thread_id}")

        current_marker = self.get_current_thread_marker()
        now = _now_iso()

        # Update the current thread marker
        if current_marker:
            marker = dict(current_marker)
            marker["Version"] = int(marker.get("Version", 0)) + 1
        else:
            marker = {
                "PK": self._pk(),
                "SK": self.CURRENT_THREAD_SK,
                "CreatedAt": now,
                "Version": 1,
            }
        marker["CurrentThreadId"] = target_thread_id
        marker["ActiveAt"] = now
        marker["UpdatedAt"] = now

        # Update the target thread's metadata with a fresh activity timestamp
        target = dict(target_meta)
        target["LastActivity"] = now
        target["UpdatedAt"] = now
        target["Version"] = int(target.get("Version", 0)) + 1

        transact_items = [
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": self._serialize_item(marker),
                }
            },
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": self._serialize_item(target),
                }
            },
        ]

        if current_marker and current_marker.get("CurrentThreadId") != target_thread_id:
            previous_thread_id = current_marker.get("CurrentThreadId")
            if previous_thread_id:
                previous_sk = f"THREAD#{previous_thread_id}#META"
                previous_meta = self._raw_get(previous_sk)
                if previous_meta:
                    previous = dict(previous_meta)
                    previous["LastActivity"] = current_marker.get("ActiveAt", now)
                    previous["UpdatedAt"] = now
                    previous["Version"] = int(previous.get("Version", 0)) + 1
                    transact_items.append(
                        {
                            "Put": {
                                "TableName": self.table_name,
                                "Item": self._serialize_item(previous),
                            }
                        }
                    )

                for agent_state in self.query_agent_states(previous_thread_id):
                    if agent_state.get("Status") == "active":
                        suspended = dict(agent_state)
                        suspended["Status"] = "suspended"
                        suspended["SuspendedAt"] = now
                        suspended["UpdatedAt"] = now
                        suspended["Version"] = int(suspended.get("Version", 0)) + 1
                        transact_items.append(
                            {
                                "Put": {
                                    "TableName": self.table_name,
                                    "Item": self._serialize_item(suspended),
                                }
                            }
                        )

        for agent_state in self.query_agent_states(target_thread_id):
            if agent_state.get("Status") == "suspended":
                resumed = dict(agent_state)
                resumed["Status"] = "active"
                resumed["ResumedAt"] = now
                resumed["UpdatedAt"] = now
                resumed["Version"] = int(resumed.get("Version", 0)) + 1
                transact_items.append(
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": self._serialize_item(resumed),
                        }
                    }
                )

        if len(transact_items) > 25:
            raise ToolError(
                f"SwThread transaction has {len(transact_items)} items — "
                "exceeds DynamoDB limit of 25. Reduce active agent count before switching."
            )
        self.transact_write_items(transact_items)
        return {
            "thread_id": target_thread_id,
            "status": "switched",
            "switched_at": now,
        }

    # ------------------------------------------------------------------
    # Private (used internally, not part of public contract)
    # ------------------------------------------------------------------

    def _raw_get(self, sk: str) -> dict | None:
        """Get item without thread isolation check (used for version fetch in put_item)."""
        response = self.table.get_item(Key={"PK": self._pk(), "SK": sk})
        return response.get("Item")
