from fastapi import Header, HTTPException

from config import settings


async def require_api_key(x_api_key: str = Header(default="")) -> str:
    expected = settings.app_api_key
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API authentication is not configured. Set APP_API_KEY in the server environment.",
        )
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return x_api_key
