"""
Story 1.3: DynamoDB Table & S3 Bucket Provisioning
Each provision_*() returns (passed: bool, message: str).
run_all() prints results and returns the count of provisioning errors.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Colour helpers (same as validate.py)
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


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def _resolve_config(plugin_dir: str = "") -> dict:
    """
    Resolve provisioning config.
    Priority: ~/.agent101/config.json → env vars → defaults.
    Default bucket name derived from AWS account ID (guarantees global uniqueness).
    """
    config_path = Path.home() / ".agent101" / "config.json"
    file_config: dict = {}
    if config_path.exists():
        try:
            file_config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    table_name = (
        file_config.get("DYNAMO_TABLE")
        or os.environ.get("DYNAMO_TABLE", "")
        or "agent101"
    )

    region = (
        file_config.get("AWS_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION", "")
        or "us-east-1"
    )

    # Bucket name: config → env → default using account ID
    bucket_name = file_config.get("S3_BUCKET") or os.environ.get("S3_BUCKET", "")
    if not bucket_name:
        try:
            import boto3  # noqa: PLC0415
            account_id = boto3.client("sts").get_caller_identity()["Account"]
            bucket_name = f"agent101-blobs-{account_id}"
        except Exception:  # noqa: BLE001
            bucket_name = "agent101-blobs"

    return {"table_name": table_name, "bucket_name": bucket_name, "region": region}


# ---------------------------------------------------------------------------
# DynamoDB provisioning
# ---------------------------------------------------------------------------

def provision_dynamodb(table_name: str) -> tuple[bool, str]:
    """
    Create DynamoDB table if absent (PAY_PER_REQUEST, PK+SK, PITR).
    Skip + validate schema if present.
    """
    try:
        import boto3  # noqa: PLC0415
        from botocore.exceptions import ClientError  # noqa: PLC0415

        client = boto3.client("dynamodb")

        # Check if table already exists
        try:
            response = client.describe_table(TableName=table_name)
            # Validate schema compatibility
            key_attrs = {k["AttributeName"] for k in response["Table"]["KeySchema"]}
            if {"PK", "SK"}.issubset(key_attrs):
                # Ensure PITR is enabled even on pre-existing tables
                pitr = client.describe_continuous_backups(TableName=table_name)
                pitr_status = (
                    pitr["ContinuousBackupsDescription"]
                    ["PointInTimeRecoveryDescription"]
                    ["PointInTimeRecoveryStatus"]
                )
                if pitr_status != "ENABLED":
                    client.update_continuous_backups(
                        TableName=table_name,
                        PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True},
                    )
                return True, _ok(f"DynamoDB table '{table_name}' already exists — skipping")
            else:
                return True, _warn(
                    f"DynamoDB table '{table_name}' exists but schema is incompatible "
                    f"(found keys: {key_attrs}). agent101 requires PK+SK. "
                    "Proceeding — rename the table in ~/.agent101/config.json if needed."
                )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        # Table does not exist — create it
        client.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Wait for ACTIVE state before enabling PITR
        waiter = client.get_waiter("table_exists")
        waiter.wait(
            TableName=table_name,
            WaiterConfig={"Delay": 2, "MaxAttempts": 20},
        )

        # PITR may not be available immediately after ACTIVE — retry up to 5×
        import time  # noqa: PLC0415
        for attempt in range(5):
            try:
                client.update_continuous_backups(
                    TableName=table_name,
                    PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True},
                )
                break
            except ClientError as e:
                if e.response["Error"]["Code"] == "ContinuousBackupsUnavailableException" and attempt < 4:
                    time.sleep(3)
                else:
                    raise

        return True, _ok(f"DynamoDB table '{table_name}' created")

    except ImportError:
        return False, _fail("DynamoDB provisioning — boto3 not installed")
    except Exception as exc:  # noqa: BLE001
        return False, _fail(f"DynamoDB provisioning failed — {exc}\n     Fix: check IAM permissions (dynamodb:CreateTable, dynamodb:UpdateContinuousBackups)")


# ---------------------------------------------------------------------------
# S3 provisioning
# ---------------------------------------------------------------------------

def provision_s3(bucket_name: str, region: str = "us-east-1") -> tuple[bool, str]:
    """
    Create S3 bucket if absent with private ACL + block public access.
    Skip if already owned by this account.
    NOTE: us-east-1 must NOT pass CreateBucketConfiguration (boto3 quirk).
    """
    try:
        import boto3  # noqa: PLC0415
        from botocore.exceptions import ClientError  # noqa: PLC0415

        client = boto3.client("s3", region_name=region)

        try:
            if region == "us-east-1":
                client.create_bucket(Bucket=bucket_name)
            else:
                client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )

            # Block all public access (security baseline)
            client.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )
            return True, _ok(f"S3 bucket '{bucket_name}' created")

        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "BucketAlreadyOwnedByYou":
                return True, _ok(f"S3 bucket '{bucket_name}' already exists — skipping")
            if code == "BucketAlreadyExists":
                return False, _fail(
                    f"S3 bucket '{bucket_name}' already exists and is owned by another account.\n"
                    "     Fix: set a unique S3_BUCKET name in ~/.agent101/config.json"
                )
            raise

    except ImportError:
        return False, _fail("S3 provisioning — boto3 not installed")
    except Exception as exc:  # noqa: BLE001
        return False, _fail(f"S3 provisioning failed — {exc}\n     Fix: check IAM permissions (s3:CreateBucket, s3:PutPublicAccessBlock)")


# ---------------------------------------------------------------------------
# run_all — called by install.sh
# ---------------------------------------------------------------------------

def run_all(plugin_dir: str = "") -> int:
    """
    Provision all AWS resources, print results, return error count.
    Caller (install.sh) always exits 0 — this is advisory.
    """
    print(f"\n\033[1mProvisioning AWS resources\033[0m")

    config = _resolve_config(plugin_dir)
    errors = 0

    passed, msg = provision_dynamodb(config["table_name"])
    print(msg)
    if not passed:
        errors += 1

    passed, msg = provision_s3(config["bucket_name"], config["region"])
    print(msg)
    if not passed:
        errors += 1

    if errors > 0:
        print(
            f"\n  {YELLOW}⚠{NC}   Provisioning: {errors} resource(s) failed. "
            "Personal mode features require DynamoDB + S3.\n"
            "     Fix the errors above then re-run ./install.sh"
        )

    return errors


# ---------------------------------------------------------------------------
# Entry point — called by install.sh as:
#   python3 "$PLUGIN_DIR/server/provision.py" "$PLUGIN_DIR"
# Always exits 0 (advisory).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    plugin_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    run_all(plugin_dir)
    sys.exit(0)
