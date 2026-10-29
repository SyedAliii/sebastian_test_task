import hashlib
import hmac


def signatures_match(raw: bytes, header: str | None, secret: str) -> bool:
    if not header:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, header)
    except Exception:
        return False
