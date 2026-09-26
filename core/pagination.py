import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException


def encode_cursor(created_at: datetime, identifier: UUID) -> str:
    value = json.dumps([created_at.isoformat(), str(identifier)], separators=(",", ":"))
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        if "=" in cursor:
            raise ValueError("Cursor must be unpadded")
        raw = base64.b64decode(
            cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True
        )
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != cursor:
            raise ValueError("Cursor is not canonical URL-safe base64")
        value = json.loads(raw)
        if not isinstance(value, list) or len(value) != 2 or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError("Cursor must contain a timestamp and UUID")
        timestamp, identifier = value
        parsed = datetime.fromisoformat(timestamp)
        if parsed.utcoffset() is None:
            raise ValueError("Cursor timestamp must include a timezone")
        return parsed, UUID(identifier)
    except (
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
    ) as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc
