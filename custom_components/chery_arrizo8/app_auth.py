"""Exchange an App refresh credential for a vehicle status access token."""

from __future__ import annotations

from aiohttp import ClientSession


UAA_REFRESH_URL = "https://uaa2c.chery.cn/api/v1/uaa/oauth/refresh-token"
TSP_TOKEN_URL = (
    "https://mobile-consumer-sapp.chery.cn"
    "/web/chery/car-service/v2/car-appsdk/getTspSdkToken"
)
APP_HEADERS = {
    "agent": "ios",
    "appversion": "3.8.1",
    "appversioncode": "26083102",
    "request-channel": "app",
}


class AppCredentialError(ValueError):
    """The App rejected the refresh credential."""


class AppTokenError(ValueError):
    """The App did not return a usable vehicle token."""


async def renew_vehicle_token(session: ClientSession, refresh_token: str) -> tuple[str, str]:
    """Return the latest App refresh credential and vehicle SDK token."""
    if not isinstance(refresh_token, str) or not refresh_token or any(c.isspace() for c in refresh_token):
        raise AppCredentialError("invalid App refresh credential")

    async with session.post(
        UAA_REFRESH_URL,
        json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        headers=APP_HEADERS,
        timeout=20,
    ) as response:
        if response.status in (401, 403):
            raise AppCredentialError("App refresh credential rejected")
        response.raise_for_status()
        payload = await response.json(content_type=None)

    if not isinstance(payload, dict):
        raise AppTokenError("unexpected App refresh response")
    if payload.get("status") != 200:
        raise AppCredentialError("App refresh credential rejected")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise AppTokenError("missing App token data")
    access = data.get("access_token")
    rotated_refresh = data.get("refresh_token") or refresh_token
    if not isinstance(access, str) or not access or not isinstance(rotated_refresh, str):
        raise AppTokenError("missing App token")

    async with session.post(
        TSP_TOKEN_URL,
        params={"access_token": access, "terminal": "3"},
        data=b"{}",
        headers={**APP_HEADERS, "content-type": "application/json; charset=UTF-8"},
        timeout=20,
    ) as response:
        if response.status in (401, 403):
            raise AppCredentialError("App token rejected by vehicle service")
        response.raise_for_status()
        payload = await response.json(content_type=None)

    if not isinstance(payload, dict) or payload.get("status") != 200:
        raise AppTokenError("vehicle token request was not accepted")
    data = payload.get("data")
    sdk_token = data.get("sdk_token") if isinstance(data, dict) else None
    if not isinstance(sdk_token, str) or sdk_token.count(".") != 2:
        raise AppTokenError("vehicle service did not return an SDK token")
    return rotated_refresh, sdk_token
