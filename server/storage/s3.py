"""
server/storage/s3.py — S3 blob storage client for agent101.

Handles content >400KB that cannot fit in a single DynamoDB item.
All blobs stored at: s3://{bucket}/{user_id}/threads/{thread_id}/{key}

Thread isolation: the key path embeds thread_id — cross-thread access
requires an explicit different thread_id, making accidental bleed impossible.
"""
import logging
from urllib.parse import urlparse

import boto3
from mcp.server.fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)


def _s3_path(user_id: str, thread_id: str, key: str) -> str:
    return f"{user_id}/threads/{thread_id}/{key}"


class S3Client:
    """
    Typed S3 client for agent101 blob storage.
    """

    def __init__(
        self,
        bucket: str,
        user_id: str = "default",
        profile: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.user_id = user_id

        session_kwargs: dict = {}
        if profile:
            session_kwargs["profile_name"] = profile

        session = boto3.Session(**session_kwargs)
        self._s3 = session.client("s3")

    def put_blob(self, thread_id: str, key: str, content: str | bytes) -> str:
        """
        Upload content to S3. Returns the s3:// URI.

        Args:
            thread_id: Thread this blob belongs to. Embedded in the S3 path.
            key: Blob key within the thread (e.g. "summary", "msg_001").
            content: String or bytes to store.

        Returns:
            s3://{bucket}/{user_id}/threads/{thread_id}/{key}
        """
        if isinstance(content, str):
            content = content.encode("utf-8")

        s3_key = _s3_path(self.user_id, thread_id, key)

        try:
            self._s3.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=content,
            )
        except Exception as exc:
            raise ToolError(f"S3 put_blob failed for '{key}': {exc}") from exc

        uri = f"s3://{self.bucket}/{s3_key}"
        logger.debug("put_blob: %s (%d bytes)", uri, len(content))
        return uri

    def get_blob(self, uri: str) -> bytes:
        """
        Download a blob by its s3:// URI. Returns raw bytes.

        Args:
            uri: s3://{bucket}/{key} URI returned by put_blob.

        Returns:
            Raw bytes content.
        """
        parsed = urlparse(uri)
        if parsed.scheme != "s3":
            raise ToolError(f"Invalid S3 URI scheme: '{uri}' (expected s3://...)")

        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        try:
            response = self._s3.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise ToolError(f"S3 get_blob failed for '{uri}': {exc}") from exc
