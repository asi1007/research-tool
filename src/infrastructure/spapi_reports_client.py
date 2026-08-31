from __future__ import annotations

import gzip
import io
import json
import logging
import time
from datetime import date
from typing import Any, Protocol

import requests

logger = logging.getLogger(__name__)

TOKEN_URL = "https://api.amazon.com/auth/o2/token"
ENDPOINT = "https://sellingpartnerapi-fe.amazon.com"
JAPAN_MARKETPLACE_ID = "A1VC38T7YXB528"
SEARCH_TERMS_REPORT_TYPE = "GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT"
TIMEOUT_SECONDS = 60
DOWNLOAD_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 15
MAX_WAIT_SECONDS = 900
DONE = "DONE"
FAILED_STATUSES = {"CANCELLED", "FATAL"}


class ReportError(RuntimeError):
    pass


class HttpSession(Protocol):
    def post(self, url: str, **kwargs: Any) -> Any: ...
    def get(self, url: str, **kwargs: Any) -> Any: ...


class SpApiReportsClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        session: HttpSession | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.session = session or requests
        self.sleep = sleep

    def fetch_search_terms_report(self, start: date, end: date) -> dict:
        report_id = self._create_report(start, end)
        document_id = self._wait_for_document(report_id)
        return self._download(document_id)

    def _create_report(self, start: date, end: date) -> str:
        response = self.session.post(
            f"{ENDPOINT}/reports/2021-06-30/reports",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "reportType": SEARCH_TERMS_REPORT_TYPE,
                "marketplaceIds": [JAPAN_MARKETPLACE_ID],
                "dataStartTime": f"{start.isoformat()}T00:00:00Z",
                "dataEndTime": f"{end.isoformat()}T00:00:00Z",
                "reportOptions": {"reportPeriod": "WEEK"},
            },
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code not in (200, 202):
            raise ReportError(f"レポートを要求できません: {response.status_code} - {response.text[:200]}")
        return response.json()["reportId"]

    def _wait_for_document(self, report_id: str) -> str:
        waited = 0
        while waited < MAX_WAIT_SECONDS:
            response = self.session.get(
                f"{ENDPOINT}/reports/2021-06-30/reports/{report_id}",
                headers=self._headers(),
                timeout=TIMEOUT_SECONDS,
            )
            payload = response.json()
            status = payload.get("processingStatus")
            if status == DONE:
                return payload["reportDocumentId"]
            if status in FAILED_STATUSES:
                raise ReportError(f"レポートの生成に失敗しました: {status} - {payload}")

            logger.info(
                "レポートの生成を待っています",
                extra={"context": {"report_id": report_id, "status": status, "waited": waited}},
            )
            self.sleep(POLL_INTERVAL_SECONDS)
            waited += POLL_INTERVAL_SECONDS

        raise ReportError(f"レポートの生成が終わりません: {report_id}")

    def _download(self, document_id: str) -> dict:
        response = self.session.get(
            f"{ENDPOINT}/reports/2021-06-30/documents/{document_id}",
            headers=self._headers(),
            timeout=TIMEOUT_SECONDS,
        )
        payload = response.json()
        content = self.session.get(payload["url"], timeout=DOWNLOAD_TIMEOUT_SECONDS).content
        if payload.get("compressionAlgorithm") == "GZIP":
            content = gzip.GzipFile(fileobj=io.BytesIO(content)).read()
        return json.loads(content.decode("utf-8"))

    def _headers(self) -> dict[str, str]:
        return {"x-amz-access-token": self._access_token()}

    def _access_token(self) -> str:
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
            raise ReportError(
                f"アクセストークンを取得できません: {response.status_code} - {response.text[:200]}"
            )
        return response.json()["access_token"]
