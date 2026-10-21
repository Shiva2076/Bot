import asyncio
import time
from datetime import date, datetime
from typing import Dict, Optional

import httpx
import pyotp
import pytz
from pydantic import BaseModel

from schemas.angel import AngelCredentials, AngelEnvelope, AngelLoginRequest, AngelLoginResponse
from services.brokers.angel.rate_limiter import SlidingWindowRateLimiter
from services.trading.errors import MarketDataUnavailableError

BASE_URL = "https://apiconnect.angelone.in"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
TOKEN_ERROR_CODES = {"AG8001", "AG8002", "AG8003"}
RATE_LIMIT_BACKOFF_SECONDS = 15.0
IST = pytz.timezone("Asia/Kolkata")


class AngelSession:
    def __init__(
        self,
        credentials: AngelCredentials,
        client: httpx.AsyncClient,
        rate_limiter: SlidingWindowRateLimiter,
        max_concurrent_requests: int,
    ):
        self._credentials = credentials
        self._client = client
        self._rate_limiter = rate_limiter
        self._max_concurrent_requests = max_concurrent_requests
        self._jwt_token: Optional[str] = None
        self._logged_in_on: Optional[date] = None
        self._login_lock: Optional[asyncio.Lock] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._cooldown_until: float = 0.0

    @property
    def is_configured(self) -> bool:
        credentials = self._credentials
        return all([credentials.api_key, credentials.client_code, credentials.pin, credentials.totp_secret])

    async def post(self, path: str, body: BaseModel) -> Dict:
        payload = await self._send(path, body)
        if self._is_token_error(payload):
            self._jwt_token = None
            payload = await self._send(path, body)
        return payload

    async def _send(self, path: str, body: BaseModel) -> Dict:
        await self._wait_out_cooldown()
        token = await self._ensure_token()
        self._semaphore = self._semaphore or asyncio.Semaphore(self._max_concurrent_requests)
        async with self._semaphore:
            await self._rate_limiter.acquire()
            response = await self._client.post(
                f"{BASE_URL}{path}",
                json=body.model_dump(by_alias=True),
                headers={**self._headers(), "Authorization": f"Bearer {token}"},
            )
        self._raise_if_rate_limited(response)
        try:
            return response.json()
        except ValueError:
            raise MarketDataUnavailableError(
                f"Angel One returned HTTP {response.status_code}: {response.text[:120].strip()}"
            )

    async def _ensure_token(self) -> str:
        self._login_lock = self._login_lock or asyncio.Lock()
        async with self._login_lock:
            today = datetime.now(IST).date()
            if self._jwt_token is None or self._logged_in_on != today:
                self._jwt_token = await self._login()
                self._logged_in_on = today
            return self._jwt_token

    async def _login(self) -> str:
        if not self.is_configured:
            raise MarketDataUnavailableError("Angel One credentials are not configured in backend/.env")
        await self._wait_out_cooldown()
        await self._rate_limiter.acquire()
        request = AngelLoginRequest(
            clientcode=self._credentials.client_code,
            password=self._credentials.pin,
            totp=pyotp.TOTP(self._credentials.totp_secret).now(),
        )
        response = await self._client.post(
            f"{BASE_URL}{LOGIN_PATH}",
            json=request.model_dump(),
            headers=self._headers(),
        )
        self._raise_if_rate_limited(response)
        login = AngelLoginResponse.model_validate(response.json())
        if not login.status or login.data is None:
            raise MarketDataUnavailableError(f"Angel One login failed: {login.message} ({login.errorcode})")
        return login.data.jwt_token

    def _raise_if_rate_limited(self, response: httpx.Response) -> None:
        body = response.text.lower()
        if response.status_code == 403 and ("access rate" in body or "rate" in body):
            self._cooldown_until = time.monotonic() + RATE_LIMIT_BACKOFF_SECONDS
            raise MarketDataUnavailableError(
                "Angel One rate limit hit. Cooling down before retry; Yahoo failover may still serve some prices."
            )

    async def _wait_out_cooldown(self) -> None:
        remaining = self._cooldown_until - time.monotonic()
        if remaining > 0:
            await asyncio.sleep(remaining)

    def _is_token_error(self, payload: Dict) -> bool:
        return AngelEnvelope.model_validate(payload).errorcode in TOKEN_ERROR_CODES

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self._credentials.api_key,
        }
