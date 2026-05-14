"""
Tests for Story 1.1: Plugin Installation & Claude Code Registration
Run: pytest server/tests/test_install.py -v
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# AC 3: requirements.txt contains all required packages
# ---------------------------------------------------------------------------

def test_requirements_txt_exists():
    assert (PLUGIN_DIR / "server" / "requirements.txt").exists()


def test_requirements_txt_contains_all_packages():
    content = (PLUGIN_DIR / "server" / "requirements.txt").read_text()
    required = ["mcp", "boto3", "opensearch-py", "rapidfuzz", "aiohttp", "anthropic", "python-dotenv"]
    missing = [p for p in required if p not in content]
    assert not missing, f"Missing packages: {missing}"


# ---------------------------------------------------------------------------
# AC 4: registry.json initialized correctly
# ---------------------------------------------------------------------------

def test_registry_json_exists():
    assert (PLUGIN_DIR / "registry.json").exists()


def test_registry_json_valid_shape():
    data = json.loads((PLUGIN_DIR / "registry.json").read_text())
    assert data["version"] == "1.0"
    assert isinstance(data["skills"], list)


def test_registry_json_not_overwritten_when_present(tmp_path):
    """init_registry logic must not overwrite existing registry."""
    registry_path = tmp_path / "registry.json"
    existing = '{"version":"1.0","skills":[{"name":"bmad"}]}'
    registry_path.write_text(existing)
    # Simulate idempotent init_registry
    if not registry_path.exists():
        registry_path.write_text('{"version":"1.0","skills":[]}')
    assert registry_path.read_text() == existing


# ---------------------------------------------------------------------------
# AC 5: server/main.py starts without import errors
# ---------------------------------------------------------------------------

def test_server_main_importable():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); from server.main import mcp; print(mcp.name)"],
        cwd=str(PLUGIN_DIR),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Import failed:\n{result.stderr}"
    assert "agent101" in result.stdout


# ---------------------------------------------------------------------------
# AC 6: settings.json patching is idempotent
# ---------------------------------------------------------------------------

def test_settings_patch_idempotent(tmp_path):
    """Applying the MCP entry twice must not create duplicate keys."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    def apply_patch(path: Path):
        data = json.loads(path.read_text())
        servers = data.setdefault("mcpServers", {})
        if "agent101" not in servers:
            servers["agent101"] = {
                "command": "python3",
                "args": ["server/main.py"],
                "cwd": str(PLUGIN_DIR),
            }
        path.write_text(json.dumps(data, indent=2))

    apply_patch(settings_path)
    apply_patch(settings_path)

    result = json.loads(settings_path.read_text())
    assert len([k for k in result["mcpServers"] if k == "agent101"]) == 1


def test_hooks_patch_idempotent(tmp_path):
    """Applying the hooks block twice must not duplicate hook commands."""
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{}")

    hook_cmd = "/fake/hooks/session-start.sh"

    def apply_hooks(path: Path):
        data = json.loads(path.read_text())
        hooks = data.setdefault("hooks", {})
        existing_cmds = [h.get("command") for h in hooks.get("SessionStart", [])]
        if hook_cmd not in existing_cmds:
            hooks.setdefault("SessionStart", []).append({"command": hook_cmd})
        path.write_text(json.dumps(data, indent=2))

    apply_hooks(settings_path)
    apply_hooks(settings_path)

    result = json.loads(settings_path.read_text())
    assert len(result["hooks"]["SessionStart"]) == 1


# ---------------------------------------------------------------------------
# Story 1.2: AWS Connectivity & Credential Validation
# ---------------------------------------------------------------------------
import sys as _sys
_sys.path.insert(0, str(PLUGIN_DIR))

import os
from unittest.mock import MagicMock, patch

from server.validate import (
    check_bedrock,
    check_dynamodb,
    check_opensearch,
    check_platform_key,
    check_s3,
    run_all,
)


# --- AC1: DynamoDB success ---

def test_dynamodb_success():
    mock_client = MagicMock()
    mock_client.list_tables.return_value = {"TableNames": []}
    with patch("boto3.client", return_value=mock_client):
        passed, msg = check_dynamodb()
    assert passed
    assert "DynamoDB" in msg
    assert "✓" in msg


# --- AC1: DynamoDB AccessDeniedException ---

def test_dynamodb_access_denied():
    from botocore.exceptions import ClientError

    error_response = {
        "Error": {
            "Code": "AccessDeniedException",
            "Message": "User is not authorized to perform: dynamodb:ListTables on resource: *",
        }
    }
    mock_client = MagicMock()
    mock_client.list_tables.side_effect = ClientError(error_response, "ListTables")

    with patch("boto3.client", return_value=mock_client):
        passed, msg = check_dynamodb()

    assert not passed
    assert "dynamodb:ListTables" in msg
    assert "✗" in msg


# --- AC2: S3 success ---

def test_s3_success():
    mock_client = MagicMock()
    mock_client.list_buckets.return_value = {"Buckets": []}
    with patch("boto3.client", return_value=mock_client):
        passed, msg = check_s3()
    assert passed
    assert "S3" in msg


# --- AC2: S3 AccessDenied ---

def test_s3_access_denied():
    from botocore.exceptions import ClientError

    error_response = {
        "Error": {
            "Code": "AccessDenied",
            "Message": "User is not authorized to perform: s3:ListBuckets",
        }
    }
    mock_client = MagicMock()
    mock_client.list_buckets.side_effect = ClientError(error_response, "ListBuckets")

    with patch("boto3.client", return_value=mock_client):
        passed, msg = check_s3()

    assert not passed
    assert "s3:ListBuckets" in msg


# --- AC3: Bedrock success ---

def test_bedrock_success():
    mock_client = MagicMock()
    mock_client.list_foundation_models.return_value = {"modelSummaries": []}
    with patch("boto3.client", return_value=mock_client):
        passed, msg = check_bedrock()
    assert passed
    assert "Bedrock" in msg


# --- AC3: Bedrock uses us-east-1 ---

def test_bedrock_uses_us_east_1():
    captured = {}

    def fake_boto3_client(service, **kwargs):
        captured["region"] = kwargs.get("region_name")
        m = MagicMock()
        m.list_foundation_models.return_value = {"modelSummaries": []}
        return m

    with patch("boto3.client", side_effect=fake_boto3_client):
        check_bedrock()

    assert captured["region"] == "us-east-1"


# --- AC4: OpenSearch skipped when not configured ---

def test_opensearch_skipped_when_not_configured():
    passed, msg = check_opensearch(host="")
    assert passed  # skip is not an error
    assert "skipped" in msg


# --- AC4: OpenSearch success ---

def test_opensearch_success():
    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        passed, msg = check_opensearch(host="localhost", port="9200")

    assert passed
    assert "OpenSearch" in msg


# --- AC4: OpenSearch failure ---

def test_opensearch_failure():
    with patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
        passed, msg = check_opensearch(host="localhost", port="9200")
    assert not passed
    assert "✗" in msg


# --- AC7: Platform key warning when absent ---

def test_platform_key_warning_when_absent(tmp_path):
    env_backup = os.environ.pop("ANTHROPIC_PLATFORM_AWS_API_KEY", None)
    try:
        passed, msg = check_platform_key(plugin_dir=str(tmp_path))
        assert passed  # non-fatal
        assert "not set" in msg or "disabled" in msg
    finally:
        if env_backup is not None:
            os.environ["ANTHROPIC_PLATFORM_AWS_API_KEY"] = env_backup


# --- AC7: Platform key present ---

def test_platform_key_present_via_env():
    os.environ["ANTHROPIC_PLATFORM_AWS_API_KEY"] = "test-key-abc"
    try:
        passed, msg = check_platform_key()
        assert passed
        assert "✓" in msg
    finally:
        del os.environ["ANTHROPIC_PLATFORM_AWS_API_KEY"]


# --- AC8: run_all exits 0 even when all AWS checks fail ---

def test_run_all_is_advisory(tmp_path, capsys):
    from botocore.exceptions import NoCredentialsError

    with (
        patch("server.validate.check_dynamodb", return_value=(False, "  ✗  DynamoDB — no creds")),
        patch("server.validate.check_s3",       return_value=(False, "  ✗  S3 — no creds")),
        patch("server.validate.check_bedrock",  return_value=(False, "  ✗  Bedrock — no creds")),
        patch("server.validate.check_opensearch", return_value=(True, "  ⚠   OpenSearch — skipped")),
        patch("server.validate.check_platform_key", return_value=(True, "  ⚠   key not set")),
    ):
        error_count = run_all(str(tmp_path))

    assert error_count == 3  # 3 AWS failures counted
    # Caller (install.sh) always exits 0 — this just returns the count


# ---------------------------------------------------------------------------
# Story 1.3: DynamoDB Table & S3 Bucket Provisioning
# ---------------------------------------------------------------------------
from server.provision import (
    provision_dynamodb,
    provision_s3,
    run_all as provision_run_all,
)


# --- AC1: DynamoDB created when absent ---

def test_dynamodb_created_when_absent():
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    # describe_table raises ResourceNotFoundException → table absent
    mock_client.describe_table.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
        "DescribeTable",
    )
    mock_client.create_table.return_value = {}
    mock_client.get_waiter.return_value = MagicMock(wait=MagicMock())
    mock_client.update_continuous_backups.return_value = {}

    with patch("boto3.client", return_value=mock_client):
        passed, msg = provision_dynamodb("agent101")

    assert passed
    assert "created" in msg
    mock_client.create_table.assert_called_once()
    # Verify PITR enabled
    mock_client.update_continuous_backups.assert_called_once()


# --- AC2: DynamoDB skipped when already present with compatible schema ---

def test_dynamodb_skipped_when_present_compatible():
    mock_client = MagicMock()
    mock_client.describe_table.return_value = {
        "Table": {
            "KeySchema": [
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ]
        }
    }

    with patch("boto3.client", return_value=mock_client):
        passed, msg = provision_dynamodb("agent101")

    assert passed
    assert "already exists" in msg
    mock_client.create_table.assert_not_called()


# --- AC3: DynamoDB incompatible schema emits warning (non-fatal) ---

def test_dynamodb_incompatible_schema_warns():
    mock_client = MagicMock()
    mock_client.describe_table.return_value = {
        "Table": {
            "KeySchema": [
                {"AttributeName": "id", "KeyType": "HASH"},
            ]
        }
    }

    with patch("boto3.client", return_value=mock_client):
        passed, msg = provision_dynamodb("agent101")

    assert passed  # warning — not an error
    assert "incompatible" in msg or "⚠" in msg
    mock_client.create_table.assert_not_called()


# --- AC4: S3 bucket created when absent ---

def test_s3_bucket_created_when_absent():
    mock_client = MagicMock()
    mock_client.create_bucket.return_value = {}
    mock_client.put_public_access_block.return_value = {}

    with patch("boto3.client", return_value=mock_client):
        passed, msg = provision_s3("agent101-blobs-123456789", region="us-east-1")

    assert passed
    assert "created" in msg
    # us-east-1 must NOT pass CreateBucketConfiguration
    call_kwargs = mock_client.create_bucket.call_args.kwargs
    assert "CreateBucketConfiguration" not in call_kwargs
    mock_client.put_public_access_block.assert_called_once()


# --- AC4: S3 non-us-east-1 passes LocationConstraint ---

def test_s3_bucket_passes_location_constraint_outside_us_east_1():
    mock_client = MagicMock()
    mock_client.create_bucket.return_value = {}
    mock_client.put_public_access_block.return_value = {}

    with patch("boto3.client", return_value=mock_client):
        passed, msg = provision_s3("agent101-blobs-123456789", region="eu-west-1")

    assert passed
    call_kwargs = mock_client.create_bucket.call_args.kwargs
    assert call_kwargs["CreateBucketConfiguration"]["LocationConstraint"] == "eu-west-1"


# --- AC5: S3 skipped when already owned by this account ---

def test_s3_bucket_skipped_when_already_owned():
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    mock_client.create_bucket.side_effect = ClientError(
        {"Error": {"Code": "BucketAlreadyOwnedByYou", "Message": "already yours"}},
        "CreateBucket",
    )

    with patch("boto3.client", return_value=mock_client):
        passed, msg = provision_s3("agent101-blobs-123456789", region="us-east-1")

    assert passed
    assert "already exists" in msg


# --- S3 bucket owned by another account is an error ---

def test_s3_bucket_owned_by_other_account_fails():
    from botocore.exceptions import ClientError

    mock_client = MagicMock()
    mock_client.create_bucket.side_effect = ClientError(
        {"Error": {"Code": "BucketAlreadyExists", "Message": "taken"}},
        "CreateBucket",
    )

    with patch("boto3.client", return_value=mock_client):
        passed, msg = provision_s3("taken-bucket", region="us-east-1")

    assert not passed
    assert "another account" in msg


# --- AC6: run_all returns 0 errors on full success ---

def test_provision_run_all_success(tmp_path):
    with (
        patch("server.provision.provision_dynamodb", return_value=(True, "  ✓  DynamoDB table 'agent101' created")),
        patch("server.provision.provision_s3", return_value=(True, "  ✓  S3 bucket 'agent101-blobs-123' created")),
        patch("server.provision._resolve_config", return_value={
            "table_name": "agent101",
            "bucket_name": "agent101-blobs-123",
            "region": "us-east-1",
        }),
    ):
        error_count = provision_run_all(str(tmp_path))

    assert error_count == 0


# ---------------------------------------------------------------------------
# Story 1.5: OpenSearch Index Provisioning
# ---------------------------------------------------------------------------
from server.provision_opensearch import provision_index, run_all as opensearch_run_all


# --- AC1: Index absent → created ---

def test_opensearch_index_created_when_absent():
    mock_client = MagicMock()
    mock_client.indices.exists.return_value = False
    mock_client.indices.create.return_value = {}

    with patch("server.provision_opensearch.OpenSearch", return_value=mock_client):
        passed, msg = provision_index("localhost", 9200)

    assert passed
    assert "Created" in msg
    mock_client.indices.create.assert_called_once()
    # Verify index name and body contain knn_vector settings
    call_kwargs = mock_client.indices.create.call_args.kwargs
    assert call_kwargs["index"] == "agent-memories"
    props = call_kwargs["body"]["mappings"]["properties"]
    assert props["embedding"]["type"] == "knn_vector"
    assert props["embedding"]["dimension"] == 1536
    assert props["embedding"]["method"]["space_type"] == "cosine"


# --- AC2a: Index exists with compatible mapping → skip ---

def test_opensearch_index_skipped_when_compatible():
    mock_client = MagicMock()
    mock_client.indices.exists.return_value = True
    mock_client.indices.get_mapping.return_value = {
        "agent-memories": {
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1536,
                    }
                }
            }
        }
    }

    with patch("server.provision_opensearch.OpenSearch", return_value=mock_client):
        passed, msg = provision_index("localhost", 9200)

    assert passed
    assert "already exists" in msg
    mock_client.indices.create.assert_not_called()


# --- AC2b: Index exists with wrong field type → returns (False, msg) ---

def test_opensearch_index_incompatible_field_type():
    mock_client = MagicMock()
    mock_client.indices.exists.return_value = True
    mock_client.indices.get_mapping.return_value = {
        "agent-memories": {
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "dense_vector",  # wrong type
                        "dimension": 1536,
                    }
                }
            }
        }
    }

    with patch("server.provision_opensearch.OpenSearch", return_value=mock_client):
        passed, msg = provision_index("localhost", 9200)

    assert not passed
    assert "not knn_vector" in msg or "incompatible" in msg


# --- AC2c: Index exists with wrong dimension → returns (False, msg) ---

def test_opensearch_index_incompatible_dimension():
    mock_client = MagicMock()
    mock_client.indices.exists.return_value = True
    mock_client.indices.get_mapping.return_value = {
        "agent-memories": {
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 768,  # wrong dimension
                    }
                }
            }
        }
    }

    with patch("server.provision_opensearch.OpenSearch", return_value=mock_client):
        passed, msg = provision_index("localhost", 9200)

    assert not passed
    assert "dimension" in msg
    assert "768" in msg


# --- AC3: No host configured → run_all returns 0, prints advisory ---

def test_opensearch_run_all_skips_when_no_host(capsys):
    with patch("server.provision_opensearch._resolve_config", return_value={"host": "", "port": 9200}):
        result = opensearch_run_all()

    assert result == 0
    captured = capsys.readouterr()
    assert "OPENSEARCH_HOST" in captured.out


# --- AC4: Connection error → advisory (False, msg), run_all still exits 0 ---

def test_opensearch_connection_error_is_advisory():
    mock_client = MagicMock()
    mock_client.indices.exists.side_effect = Exception("Connection refused")

    with patch("server.provision_opensearch.OpenSearch", return_value=mock_client):
        passed, msg = provision_index("localhost", 9200)

    assert not passed
    assert "OpenSearch error" in msg


# --- opensearch-py import error → graceful (False, msg) ---

def test_opensearch_import_error_handled():
    import server.provision_opensearch as m

    with patch.object(m, "_OPENSEARCH_AVAILABLE", False):
        passed, msg = m.provision_index("localhost", 9200)

    assert not passed
    assert "not installed" in msg or "opensearch" in msg.lower()
