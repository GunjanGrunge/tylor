"""
Story 1.2: Optional AWS Connectivity & Credential Validation
Each check_*() returns (passed: bool, message: str).
run_all() prints results and returns the count of failed optional checks.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Colour helpers (ANSI — safe on macOS/Linux terminals)
# ---------------------------------------------------------------------------
GREEN  = "\033[0;32m"
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
NC     = "\033[0m"

def _ok(msg: str) -> str:
    return f"  {GREEN}✓{NC}  {msg}"

def _fail(msg: str) -> str:
    return f"  {RED}✗{NC}  {msg}"

def _warn(msg: str) -> str:
    return f"  {YELLOW}⚠{NC}   {msg}"


def _optional_aws_enabled() -> bool:
    """Return True only when the user explicitly opts into AWS-backed features."""
    return os.environ.get("AGENT101_ENABLE_AWS", "").lower() in {"1", "true", "yes"} or os.environ.get(
        "TYLOR_ENABLE_AWS", ""
    ).lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# IAM action extraction helper
# ---------------------------------------------------------------------------
_IAM_RE = re.compile(r"(dynamodb:\w+|s3:\w+|bedrock:\w+|iam:\w+|sts:\w+)")

def _extract_iam_action(error_message: str, fallback: str) -> str:
    m = _IAM_RE.search(error_message)
    return m.group(1) if m else fallback


# ---------------------------------------------------------------------------
# Individual service checks
# ---------------------------------------------------------------------------

def check_dynamodb() -> tuple[bool, str]:
    """Test DynamoDB connectivity using list_tables."""
    try:
        import boto3  # noqa: PLC0415
        from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

        boto3.client("dynamodb").list_tables(Limit=1)
        return True, _ok("DynamoDB")
    except ImportError:
        return False, _fail("DynamoDB — boto3 not installed")
    except Exception as exc:  # noqa: BLE001
        try:
            from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

            if isinstance(exc, NoCredentialsError):
                return False, _fail("DynamoDB — no AWS credentials found")
            if isinstance(exc, ClientError):
                code = exc.response["Error"]["Code"]
                msg  = exc.response["Error"]["Message"]
                action = _extract_iam_action(msg, code)
                return False, _fail(f"DynamoDB — missing permission: {action}")
        except ImportError:
            pass
        return False, _fail(f"DynamoDB — {exc}")


def check_s3() -> tuple[bool, str]:
    """Test S3 connectivity using list_buckets."""
    try:
        import boto3  # noqa: PLC0415
        from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

        boto3.client("s3").list_buckets()
        return True, _ok("S3")
    except ImportError:
        return False, _fail("S3 — boto3 not installed")
    except Exception as exc:  # noqa: BLE001
        try:
            from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

            if isinstance(exc, NoCredentialsError):
                return False, _fail("S3 — no AWS credentials found")
            if isinstance(exc, ClientError):
                code = exc.response["Error"]["Code"]
                msg  = exc.response["Error"]["Message"]
                action = _extract_iam_action(msg, code)
                return False, _fail(f"S3 — missing permission: {action}")
        except ImportError:
            pass
        return False, _fail(f"S3 — {exc}")


def check_bedrock() -> tuple[bool, str]:
    """Test Bedrock connectivity using list_foundation_models (us-east-1 only)."""
    try:
        import boto3  # noqa: PLC0415
        from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

        # Architecture mandates us-east-1 for Bedrock — hard-coded intentionally.
        boto3.client("bedrock", region_name="us-east-1").list_foundation_models()
        return True, _ok("Bedrock")
    except ImportError:
        return False, _fail("Bedrock — boto3 not installed")
    except Exception as exc:  # noqa: BLE001
        try:
            from botocore.exceptions import ClientError, NoCredentialsError  # noqa: PLC0415

            if isinstance(exc, NoCredentialsError):
                return False, _fail("Bedrock — no AWS credentials found")
            if isinstance(exc, ClientError):
                code = exc.response["Error"]["Code"]
                msg  = exc.response["Error"]["Message"]
                action = _extract_iam_action(msg, code)
                return False, _fail(f"Bedrock — missing permission: {action}")
        except ImportError:
            pass
        return False, _fail(f"Bedrock — {exc}")


def check_opensearch(host: str = "", port: str = "9200") -> tuple[bool, str]:
    """
    Test OpenSearch cluster health via HTTP GET.
    Returns (True, advisory_warn_msg) when host is not configured — skipped is not an error.
    """
    if not host:
        return True, _warn("OpenSearch — not configured (skipped)")

    url = f"http://{host}:{port}/_cluster/health"
    try:
        urllib.request.urlopen(url, timeout=5)  # noqa: S310
        return True, _ok("OpenSearch")
    except Exception as exc:  # noqa: BLE001
        return False, _fail(f"OpenSearch — {exc}")


def check_platform_key(plugin_dir: str | Path = "") -> tuple[bool, str]:
    """
    Check for ANTHROPIC_PLATFORM_AWS_API_KEY — non-fatal, always returns True.
    Resolution order: env var → plugin_dir/.env file.
    """
    key = os.environ.get("ANTHROPIC_PLATFORM_AWS_API_KEY", "")

    if not key and plugin_dir:
        env_file = Path(plugin_dir) / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_PLATFORM_AWS_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break

    if not key:
        return True, _warn(
            "ANTHROPIC_PLATFORM_AWS_API_KEY not set — token overflow fallback disabled.\n"
            "     Set it in ~/.agent101/config.json or .env to enable Claude Platform on AWS fallback."
        )
    return True, _ok("ANTHROPIC_PLATFORM_AWS_API_KEY present")


# ---------------------------------------------------------------------------
# OpenSearch host resolution
# ---------------------------------------------------------------------------

def _resolve_opensearch_host() -> tuple[str, str]:
    """
    Resolution order:
    1. ~/.agent101/config.json → OPENSEARCH_HOST / OPENSEARCH_PORT
    2. Environment variables OPENSEARCH_HOST / OPENSEARCH_PORT
    3. Empty string → caller interprets as "not configured"
    """
    config_path = Path.home() / ".agent101" / "config.json"
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    host = config.get("OPENSEARCH_HOST") or os.environ.get("OPENSEARCH_HOST", "")
    port = config.get("OPENSEARCH_PORT") or os.environ.get("OPENSEARCH_PORT", "9200")
    return host, str(port)


# ---------------------------------------------------------------------------
# run_all — called by install.sh
# ---------------------------------------------------------------------------

def run_all(plugin_dir: str = "") -> int:
    """
    Run service checks, print results, return count of failed optional checks.
    Local JSON mode is the default and requires no AWS/OpenSearch credentials.
    """
    print(f"\n\033[1mValidating agent101 local-first setup\033[0m")

    aws_errors = 0

    if _optional_aws_enabled():
        print(_warn("AWS mode enabled — validating optional DynamoDB/S3/Bedrock services"))
        for check_fn in (check_dynamodb, check_s3, check_bedrock):
            passed, message = check_fn()
            print(message)
            if not passed:
                aws_errors += 1
    else:
        print(_ok("Local JSON storage mode — AWS validation skipped"))

    host, port = _resolve_opensearch_host()
    if host:
        passed, message = check_opensearch(host, port)
        print(message)
        if not passed:
            aws_errors += 1
    else:
        print(_warn("OpenSearch not configured — semantic recall is disabled, thread storage still works"))

    # Platform key — non-fatal, never increments aws_errors
    _, message = check_platform_key(plugin_dir)
    print(message)

    if aws_errors > 0:
        print(
            f"\n  {YELLOW}⚠{NC}   AWS validation: {aws_errors} service(s) unreachable. "
            "Optional cloud features require working AWS/OpenSearch credentials.\n"
            "     Local thread management continues to work without them."
        )

    return aws_errors


# ---------------------------------------------------------------------------
# Entry point — called by install.sh as:
#   python3 "$PLUGIN_DIR/server/validate.py" "$PLUGIN_DIR"
# Always exits 0 (advisory only).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    plugin_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    run_all(plugin_dir)
    sys.exit(0)
