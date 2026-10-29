import hashlib
import hmac


def sign_body(raw: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
