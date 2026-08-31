from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import requests

from src.domain.value_objects.asin import Asin

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
REGION_BASE_URLS = {
    "NA": "https://advertising-api.amazon.com",
    "EU": "https://advertising-api-eu.amazon.com",
    "FE": "https://advertising-api-fe.amazon.com",
}
KEYWORD_RECOMMENDATIONS_PATH = "/sp/targets/keywords/recommendations"
KEYWORD_MEDIA_TYPE = "application/vnd.spkeywordsrecommendation.v5+json"
TIMEOUT_SECONDS = 60
TOKEN_TTL_SECONDS = 3600
TOKEN_EXPIRY_MARGIN_SECONDS = 60
MAX_RECOMMENDATIONS = 10


class AdsApiError(RuntimeError):
    pass


class HttpSession(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...


class AmazonAdsClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        profile_id: str,
        region: str = "FE",
        session: HttpSession | None = None,
        clock: Any = time,
    ) -> None:
        if region not in REGION_BASE_URLS:
            raise ValueError(f"region は NA / EU / FE のいずれかです: {region}")
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.profile_id = profile_id
        self.base_url = REGION_BASE_URLS[region]
        self.session = session or requests
        self.clock = clock
        self._access_token: str | None = None
        self._token_expiry: float = 0

    def fetch_keyword_recommendations(self, asin: Asin) -> dict:
        response = self.session.post(
            f"{self.base_url}{KEYWORD_RECOMMENDATIONS_PATH}",
            headers=self._headers(),
            json={
                "recommendationType": "KEYWORDS_FOR_ASINS",
                "asins": [str(asin)],
                "maxRecommendations": MAX_RECOMMENDATIONS,
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise AdsApiError(
                f"Ads API error: {response.status_code} - {response.text[:200]}"
            )
        return response.json()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Amazon-Advertising-API-ClientId": self.client_id,
            "Amazon-Advertising-API-Scope": self.profile_id,
            "Content-Type": KEYWORD_MEDIA_TYPE,
            "Accept": KEYWORD_MEDIA_TYPE,
        }

    def _get_access_token(self) -> str:
        if self._access_token and self.clock.time() < self._token_expiry:
            return self._access_token

        response = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise AdsApiError(
                f"アクセストークンを取得できません: {response.status_code} - {response.text[:200]}"
            )

        payload = response.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", TOKEN_TTL_SECONDS)
        self._token_expiry = self.clock.time() + expires_in - TOKEN_EXPIRY_MARGIN_SECONDS
        return self._access_token
