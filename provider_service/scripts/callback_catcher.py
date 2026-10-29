import hashlib
import hmac
import os

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/provider/callback")
async def provider_callback(request: Request) -> dict[str, str]:
    raw = await request.body()
    signature = request.headers.get("X-Signature", "")
    secret = os.environ.get("PROVIDER_HMAC_SECRET", "test-secret")
    expected = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(expected, signature)
    print(raw.decode("utf-8"), flush=True)
    print(f"X-Signature: {signature}", flush=True)
    print(f"signature_ok={'true' if ok else 'false'}", flush=True)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
