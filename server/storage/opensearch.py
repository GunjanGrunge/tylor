"""
server/storage/opensearch.py — OpenSearch vector client for agent101.

Handles semantic memory: embedding via Amazon Titan Embeddings v2 (1536-dim)
through AWS Bedrock, then k-NN search against the agent-memories index.

Thread isolation is enforced at query time via a term filter on thread_id.
Facts from other threads are NEVER returned.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

import boto3
from mcp.server.fastmcp.exceptions import ToolError
from opensearchpy import OpenSearch

logger = logging.getLogger(__name__)

INDEX = "agent-memories"
TITAN_MODEL = "amazon.titan-embed-text-v2:0"
VECTOR_DIM = 1536


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OpenSearchClient:
    """
    Semantic memory client backed by OpenSearch k-NN + Bedrock Titan Embeddings v2.
    """

    def __init__(
        self,
        host: str,
        port: int = 9200,
        bedrock_region: str = "us-east-1",
        profile: str | None = None,
    ) -> None:
        self.host = host
        self.port = port

        self._os = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_compress=True,
        )

        session_kwargs: dict = {}
        if profile:
            session_kwargs["profile_name"] = profile
        session = boto3.Session(**session_kwargs)
        self._bedrock = session.client("bedrock-runtime", region_name=bedrock_region)

    # ------------------------------------------------------------------
    # Embedding helper
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list:
        """Embed text using Titan Embeddings v2. Returns 1536-dim float list."""
        try:
            response = self._bedrock.invoke_model(
                modelId=TITAN_MODEL,
                body=json.dumps({"inputText": text}),
                contentType="application/json",
                accept="application/json",
            )
            embedding = json.loads(response["body"].read())["embedding"]
        except Exception as exc:
            raise ToolError(f"Bedrock embedding failed: {exc}") from exc

        if len(embedding) != VECTOR_DIM:
            raise ToolError(
                f"Unexpected embedding dimension {len(embedding)} (expected {VECTOR_DIM})"
            )
        return embedding

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_memory(
        self,
        thread_id: str,
        fact: str,
        metadata: dict | None = None,
    ) -> str:
        """
        Embed fact via Titan v2 and write to agent-memories index.

        Args:
            thread_id: Thread this fact belongs to (stored for isolation filtering).
            fact: Plain-text fact to embed and store.
            metadata: Optional extra fields stored alongside the fact.

        Returns:
            OpenSearch document ID.
        """
        embedding = self._embed(fact)
        doc_id = uuid.uuid4().hex

        doc = {
            "thread_id": thread_id,
            "content": fact,
            "embedding": embedding,
            "created_at": _now_iso(),
        }
        if metadata:
            doc.update(metadata)

        try:
            self._os.index(index=INDEX, id=doc_id, body=doc, refresh=True)
        except Exception as exc:
            raise ToolError(f"OpenSearch index_memory failed: {exc}") from exc

        logger.debug("index_memory: doc_id=%s thread=%s", doc_id, thread_id)
        return doc_id

    def search_memory(
        self,
        thread_id: str,
        query: str,
        k: int = 5,
        type: str | None = None,
    ) -> list:
        """
        k-NN search scoped to thread_id. Never returns other threads' facts.

        Args:
            thread_id: Only return facts belonging to this thread.
            query: Natural-language query string to embed and search.
            k: Max results to return.

        Returns:
            List of dicts with keys: id, content, thread_id, created_at, score.
        """
        query_vec = self._embed(query)

        must = [
            {
                "knn": {
                    "embedding": {
                        "vector": query_vec,
                        "k": k,
                    }
                }
            },
            {"term": {"thread_id": thread_id}},
        ]
        if type:
            must.append({"term": {"type": type}})

        os_query = {
            "size": k,
            "query": {
                "bool": {
                    "must": must
                }
            },
            "_source": {"excludes": ["embedding"]},
        }

        try:
            response = self._os.search(index=INDEX, body=os_query)
        except Exception as exc:
            raise ToolError(f"OpenSearch search_memory failed: {exc}") from exc

        hits = response.get("hits", {}).get("hits", [])
        results = []
        for hit in hits:
            src = hit.get("_source", {})
            # Enforce isolation at result layer too (defence in depth)
            if src.get("thread_id") != thread_id:
                logger.warning(
                    "search_memory: skipping result with wrong thread_id '%s' (expected '%s')",
                    src.get("thread_id"),
                    thread_id,
                )
                continue
            results.append(
                {
                    "id": hit["_id"],
                    "content": src.get("content", ""),
                    "thread_id": src.get("thread_id"),
                    "created_at": src.get("created_at"),
                    "type": src.get("type"),
                    "last_used_at": src.get("last_used_at"),
                    "score": hit.get("_score"),
                }
            )

        return results
