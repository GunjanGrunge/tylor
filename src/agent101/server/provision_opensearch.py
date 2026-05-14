"""
server/provision_opensearch.py — Provision the agent-memories OpenSearch index.
Advisory: never blocks install (always exits 0).

Run standalone: python3 server/provision_opensearch.py
"""
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from opensearchpy import OpenSearch
    _OPENSEARCH_AVAILABLE = True
except ImportError:
    OpenSearch = None  # type: ignore[assignment,misc]
    _OPENSEARCH_AVAILABLE = False

INDEX_NAME = "agent-memories"
VECTOR_DIM = 1536
VECTOR_FIELD = "embedding"
SIMILARITY = "cosine"

INDEX_BODY = {
    "settings": {
        "index": {
            "knn": True,
        }
    },
    "mappings": {
        "properties": {
            VECTOR_FIELD: {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": SIMILARITY,
                    "engine": "lucene",
                },
            },
            "thread_id": {"type": "keyword"},
            "content": {"type": "text"},
            "created_at": {"type": "date"},
        }
    },
}


def _resolve_config() -> dict:
    """Read host/port from env vars then ~/.agent101/config.json."""
    cfg_path = Path.home() / ".agent101" / "config.json"
    file_cfg: dict = {}
    if cfg_path.exists():
        try:
            file_cfg = json.loads(cfg_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    host = os.getenv("OPENSEARCH_HOST") or file_cfg.get("opensearch_host", "")
    port = int(os.getenv("OPENSEARCH_PORT") or file_cfg.get("opensearch_port", 9200))
    return {"host": host, "port": port}


def provision_index(host: str, port: int) -> tuple:
    """
    Create or validate the agent-memories index.

    Returns:
        (True, message)  — success (created or already compatible)
        (False, message) — advisory failure (incompatible mapping or connection error)
    """
    if not _OPENSEARCH_AVAILABLE or OpenSearch is None:
        return False, "opensearch-py not installed — cannot provision index"

    client = OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_compress=True,
    )

    try:
        if client.indices.exists(index=INDEX_NAME):
            # Validate compatibility: knn_vector field with correct dimension
            mapping = client.indices.get_mapping(index=INDEX_NAME)
            props = (
                mapping.get(INDEX_NAME, {})
                .get("mappings", {})
                .get("properties", {})
            )
            emb = props.get(VECTOR_FIELD, {})

            if emb.get("type") != "knn_vector":
                return (
                    False,
                    f"Index '{INDEX_NAME}' exists but '{VECTOR_FIELD}' field is not knn_vector "
                    f"(got '{emb.get('type', 'missing')}') — incompatible mapping",
                )

            dim = emb.get("dimension")
            if dim is not None and int(dim) != VECTOR_DIM:
                return (
                    False,
                    f"Index '{INDEX_NAME}' exists but dimension={dim} "
                    f"(expected {VECTOR_DIM}) — incompatible mapping",
                )

            return True, f"Index '{INDEX_NAME}' already exists with compatible mapping — skipping"

        else:
            client.indices.create(index=INDEX_NAME, body=INDEX_BODY)
            return (
                True,
                f"Created index '{INDEX_NAME}' "
                f"(knn_vector, {VECTOR_DIM}-dim, {SIMILARITY})",
            )

    except Exception as exc:  # noqa: BLE001
        return False, f"OpenSearch error: {exc}"


def run_all() -> int:
    """Advisory provisioning — always exits 0."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = _resolve_config()
    host = cfg["host"]
    port = cfg["port"]

    if not host:
        print(
            "  \033[1;33m⚠\033[0m  OPENSEARCH_HOST not configured — "
            "skipping OpenSearch index provisioning"
        )
        print(
            "     Set OPENSEARCH_HOST in .env or ~/.agent101/config.json "
            "to enable semantic memory recall"
        )
        return 0

    print("\n\033[1mProvisioning OpenSearch index\033[0m")
    ok, msg = provision_index(host, port)
    if ok:
        print(f"  \033[0;32m✓\033[0m  {msg}")
    else:
        print(f"  \033[1;33m⚠\033[0m  {msg}")
        print("     recall_memory will be unavailable until the index is provisioned")

    return 0


if __name__ == "__main__":
    sys.exit(run_all())
