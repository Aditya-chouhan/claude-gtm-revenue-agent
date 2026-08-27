# Integration contracts

The repository models three activation surfaces. The FastAPI service exposes preview endpoints only:

```text
GET /v1/integrations/salesforce/accounts/{account_id}/preview
GET /v1/integrations/hubspot/accounts/{account_id}/preview
GET /v1/integrations/clay/accounts/{account_id}/preview
```

## Salesforce

The adapter models an Account upsert by `GTM_External_Key__c` and maps the deterministic score, policy version, signal date/count, latest agent brief, and data-boundary notice to custom fields. A real org must create those fields and grant field-level access; this repository does not claim that metadata is deployed.

## HubSpot

The adapter models a company update by custom unique property `gtm_external_key`. It maps the same trigger fields plus qualification and outreach angle. A real portal must create the custom properties first.

## Clay

The adapter models a webhook row containing the account key, source-derived values, latest brief, and data-boundary label. It requires a configured webhook URL and a separate shared secret header.

## Write guard

Calling any adapter's `deliver()` raises unless the global write switch, provider switch, and credentials are present. No deliver route is included in the public API. This is deliberate: the project demonstrates the contract and safety model without manufacturing credentials or a sync result.

The `deliveries` table reserves an idempotent audit surface for a future explicitly authorized delivery endpoint. It is not populated by previews.
