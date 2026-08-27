from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from revenue_agent.config import Settings
from revenue_agent.gateways.base import BaseGateway
from revenue_agent.models import Account


def _common_payload(session: Session, account: Account, gateway: BaseGateway) -> dict[str, Any]:
    return {
        "external_key": f"openfda:{account.normalized_name}",
        "account_name": account.name,
        "gtm_score": account.score,
        "score_policy": account.score_breakdown.get("policy_version"),
        "latest_signal_date": account.score_breakdown.get("latest_signal_date"),
        "signal_count": account.enrichment.get("signal_count", 0),
        "source": "openfda",
        "agent_brief": gateway.latest_brief(session, account),
        "data_boundary": "real public signals; model/mock brief labelled in agent run",
    }


class SalesforceGateway(BaseGateway):
    provider = "salesforce"

    def missing_configuration(self) -> list[str]:
        missing: list[str] = []
        if not self.settings.salesforce_live_enabled:
            missing.append("SALESFORCE_LIVE_ENABLED")
        if not self.settings.salesforce_instance_url:
            missing.append("SALESFORCE_INSTANCE_URL")
        if not self.settings.salesforce_access_token:
            missing.append("SALESFORCE_ACCESS_TOKEN")
        return missing

    def build_payload(self, session: Session, account: Account) -> dict[str, Any]:
        common = _common_payload(session, account, self)
        return {
            "Name": common["account_name"],
            "GTM_External_Key__c": common["external_key"],
            "GTM_Score__c": common["gtm_score"],
            "GTM_Score_Policy__c": common["score_policy"],
            "Latest_GTM_Signal_Date__c": common["latest_signal_date"],
            "GTM_Signal_Count__c": common["signal_count"],
            "GTM_Agent_Brief__c": common["agent_brief"],
            "GTM_Data_Boundary__c": common["data_boundary"],
        }

    def deliver(self, session: Session, account: Account) -> dict[str, Any]:
        self.assert_live_write_enabled()
        payload = self.build_payload(session, account)
        key = quote(payload["GTM_External_Key__c"], safe="")
        instance_url = self.settings.salesforce_instance_url
        if instance_url is None:
            raise RuntimeError("Salesforce instance URL disappeared after configuration check")
        url = (
            f"{instance_url.rstrip('/')}"
            f"/services/data/v61.0/sobjects/Account/GTM_External_Key__c/{key}"
        )
        token = self.settings.salesforce_access_token.get_secret_value()  # type: ignore[union-attr]
        response = httpx.patch(
            url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=20
        )
        response.raise_for_status()
        return {
            "status_code": response.status_code,
            "body": response.json() if response.content else {},
        }


class HubSpotGateway(BaseGateway):
    provider = "hubspot"

    def missing_configuration(self) -> list[str]:
        missing: list[str] = []
        if not self.settings.hubspot_live_enabled:
            missing.append("HUBSPOT_LIVE_ENABLED")
        if not self.settings.hubspot_access_token:
            missing.append("HUBSPOT_ACCESS_TOKEN")
        return missing

    def build_payload(self, session: Session, account: Account) -> dict[str, Any]:
        common = _common_payload(session, account, self)
        brief = common["agent_brief"] or {}
        return {
            "properties": {
                "name": common["account_name"],
                "gtm_external_key": common["external_key"],
                "gtm_score": str(common["gtm_score"]),
                "gtm_score_policy": common["score_policy"],
                "latest_gtm_signal_date": common["latest_signal_date"],
                "gtm_signal_count": str(common["signal_count"]),
                "gtm_qualification": brief.get("qualification"),
                "gtm_outreach_angle": brief.get("outreach_angle"),
                "gtm_data_boundary": common["data_boundary"],
            }
        }

    def deliver(self, session: Session, account: Account) -> dict[str, Any]:
        self.assert_live_write_enabled()
        key = quote(f"openfda:{account.normalized_name}", safe="")
        url = f"https://api.hubapi.com/crm/v3/objects/companies/{key}?idProperty=gtm_external_key"
        token = self.settings.hubspot_access_token.get_secret_value()  # type: ignore[union-attr]
        response = httpx.patch(
            url,
            json=self.build_payload(session, account),
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        response.raise_for_status()
        return {"status_code": response.status_code, "body": response.json()}


class ClayGateway(BaseGateway):
    provider = "clay"

    def missing_configuration(self) -> list[str]:
        missing: list[str] = []
        if not self.settings.clay_live_enabled:
            missing.append("CLAY_LIVE_ENABLED")
        if not self.settings.clay_webhook_url:
            missing.append("CLAY_WEBHOOK_URL")
        if not self.settings.clay_webhook_secret:
            missing.append("CLAY_WEBHOOK_SECRET")
        return missing

    def build_payload(self, session: Session, account: Account) -> dict[str, Any]:
        return _common_payload(session, account, self)

    def deliver(self, session: Session, account: Account) -> dict[str, Any]:
        self.assert_live_write_enabled()
        secret = self.settings.clay_webhook_secret.get_secret_value()  # type: ignore[union-attr]
        response = httpx.post(
            self.settings.clay_webhook_url,  # type: ignore[arg-type]
            json=self.build_payload(session, account),
            headers={"x-webhook-secret": secret},
            timeout=20,
        )
        response.raise_for_status()
        return {
            "status_code": response.status_code,
            "body": response.json() if response.content else {},
        }


def gateway_for(provider: str, settings: Settings) -> BaseGateway:
    gateways = {
        "salesforce": SalesforceGateway,
        "hubspot": HubSpotGateway,
        "clay": ClayGateway,
    }
    try:
        return gateways[provider](settings)
    except KeyError as exc:
        raise ValueError(f"Unsupported integration provider: {provider}") from exc
