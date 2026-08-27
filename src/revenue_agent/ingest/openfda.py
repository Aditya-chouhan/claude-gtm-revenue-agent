from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

OPENFDA_ENDPOINT = "https://api.fda.gov/drug/enforcement.json"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE = PROJECT_ROOT / "data" / "real" / "openfda_snapshot.json"


def normalize_company_name(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def parse_openfda_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def evidence_url(recall_number: str) -> str:
    query = urlencode({"search": f'recall_number:"{recall_number}"', "limit": 1})
    return f"{OPENFDA_ENDPOINT}?{query}"


class OpenFDASource:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout_seconds,
            headers={"User-Agent": "claude-gtm-revenue-agent/0.1 (portfolio project)"},
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def fetch_live(self, limit: int) -> tuple[list[dict[str, Any]], datetime]:
        params: dict[str, str | int] = {"limit": limit, "sort": "report_date:desc"}
        if self.api_key:
            params["api_key"] = self.api_key
        response = self.client.get(OPENFDA_ENDPOINT, params=params)
        response.raise_for_status()
        body = response.json()
        records = body.get("results", [])
        if not isinstance(records, list):
            raise ValueError("openFDA response field 'results' was not a list")
        return records, datetime.now(UTC)

    @staticmethod
    def fetch_fixture(path: Path = DEFAULT_FIXTURE) -> tuple[list[dict[str, Any]], datetime]:
        body = json.loads(path.read_text(encoding="utf-8"))
        if body.get("data_classification") != "real_public_data":
            raise ValueError("Fixture must declare data_classification=real_public_data")
        fetched_at = datetime.fromisoformat(body["fetched_at"].replace("Z", "+00:00"))
        records = body.get("records", [])
        if not isinstance(records, list):
            raise ValueError("Fixture field 'records' must be a list")
        return records, fetched_at
