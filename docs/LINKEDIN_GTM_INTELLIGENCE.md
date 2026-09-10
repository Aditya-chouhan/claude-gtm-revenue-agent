# LinkedIn GTM Intelligence Engine

## Goal

Extend the Claude GTM Revenue Agent from market-signal intelligence into people, account, relationship, and content intelligence while preserving the repository's evidence-first design.

This module is intentionally **human-in-the-loop**. It does not scrape LinkedIn, auto-send connection requests, auto-comment, auto-like, or auto-DM. LinkedIn-derived inputs must come from user-provided/exported data or permitted integrations. Public web/company signals can be ingested separately with provenance.

## Core workflow

```text
LinkedIn/exported data     Public company signals      CRM data
        |                          |                       |
        +--------------------------+-----------------------+
                                   |
                                   v
                            Signal ingestion
                                   |
                  +----------------+----------------+
                  v                v                v
                People          Accounts          Content
             intelligence     intelligence     intelligence
                  |                |                |
                  +----------------+----------------+
                                   |
                                   v
                         Deterministic scoring
                                   |
                                   v
                            Claude reasoning
                                   |
                      +------------+------------+
                      v            v            v
                  Who matters?   Why now?    What action?
                      +------------+------------+
                                   |
                                   v
                           Next-best action
                                   |
                                   v
                           Human approval gate
                                   |
                      +------------+------------+
                      v            v            v
                 Comment draft  Connect draft   DM draft
                                   |
                                   v
                                  CRM
```

## Intelligence layers

### 1. ICP and person intelligence

Represent a target persona with explicit criteria such as role, seniority, company size, industry, geography, relevant signals, and disqualifiers. Produce an explainable person-fit score; never allow the LLM to silently alter deterministic scoring.

### 2. Account intelligence

Combine company fit, trigger/timing signals, relationship coverage, and engagement evidence. Keep each component separately inspectable. An overall opportunity score must include its formula/version and evidence IDs.

### 3. Buying committee map

Model likely economic buyers, champions, influencers, and users. Treat role classification as an inference with confidence and evidence rather than a fact unless directly supported.

### 4. Why-now signal engine

Normalize events such as role changes, hiring, funding, product launches, leadership changes, expansion, relevant public posts, and relationship activity. Every signal requires source, timestamp, and provenance.

### 5. Content opportunity intelligence

Rank posts/conversations where the operator has a legitimate opportunity to contribute. Claude may draft multiple approaches: add insight, challenge an assumption constructively, share relevant experience, or ask a substantive question. Generic engagement bait should score poorly.

### 6. Relationship graph

Represent people, companies, interactions, and known relationships as a graph-friendly model. Derive relationship strength, account coverage, buying-committee coverage, and possible warm paths only from available evidence.

### 7. Next-best-action engine

Candidate actions include research, monitor, engage with content, connect, draft a message, nurture, escalate, or disqualify. Separate deterministic eligibility/guardrails from Claude's recommendation. Each recommendation returns rationale, confidence, evidence IDs, and an approval requirement.

### 8. Outreach intelligence

Draft messaging according to relationship stage (cold, engaged, connected, conversation, qualified, opportunity). Drafts are suggestions only. Sending remains outside the autonomous agent boundary unless a permitted provider integration and explicit human action are introduced later.

## Proposed scoring model

Keep scores modular rather than pretending one number is ground truth:

```text
ICP fit               0-100
Timing / why-now       0-100
Relationship strength 0-100
Engagement relevance  0-100
Account coverage       0-100
```

A configurable `opportunity_score_v1` can combine these components, but its weights must be disclosed and versioned. Claude receives the components and explanation; it cannot rewrite them.

## Suggested data model

- `people`
- `accounts`
- `person_account_roles`
- `relationship_edges`
- `content_items`
- `engagement_events`
- `gtm_signals`
- `score_runs`
- `recommendations`
- `draft_actions`
- `approval_events`
- `activation_receipts`

Every generated recommendation should be reproducible from stored inputs, prompt version, model, tool trace, and evidence IDs.

## Proposed API

```text
POST /v1/linkedin/import/people
POST /v1/linkedin/import/content
GET  /v1/people
GET  /v1/people/{id}
GET  /v1/accounts/{id}/buying-committee
GET  /v1/accounts/{id}/relationship-map
GET  /v1/content/opportunities
POST /v1/content/{id}/analyze
POST /v1/recommendations/run
GET  /v1/recommendations
POST /v1/recommendations/{id}/draft
POST /v1/drafts/{id}/approve
POST /v1/drafts/{id}/reject
GET  /v1/gtm/command-center
```

## Recruiter-facing command center

Navigation:

`Command Center · Accounts · People · Signals · Relationships · Content Opportunities · Engagement Queue · Outreach · Pipeline · Experiments · Evaluations · Integrations · Agent Traces`

A recommendation card should show:

```text
Person: VP Revenue — Example Co
ICP fit: 92
Timing: 96
Relationship: 71

Why now:
- recent role change [signal-123]
- company hiring GTM roles [signal-128]
- relevant public content [signal-131]

Recommendation: ENGAGE_WITH_CONTENT
Rationale: establish context before outreach
Confidence: high

[Generate drafts] [Approve] [Skip]
```

## Safety and integrity boundaries

1. No LinkedIn credential collection.
2. No browser automation against LinkedIn.
3. No automatic likes, comments, follows, connection requests, or DMs.
4. No fabricated relationship, engagement, pipeline, meeting, or revenue metrics.
5. Imported LinkedIn data is labelled by source and import time.
6. Public-web observations retain source URLs and timestamps.
7. Claude cannot mutate deterministic scores.
8. Every externally visible draft requires human review by default.
9. CRM/integration writes remain fail-closed and receipt-backed.
10. Demo/simulated/measured/live states must be visually distinct.

## Build phases

### Phase 1 — Intelligence MVP

Import user-provided people/account data; normalize people/accounts; add ICP scoring; ingest public account signals; implement why-now scoring; expose people/account endpoints; generate evidence-grounded Claude recommendations.

### Phase 2 — Content and engagement

Import user-provided post/content data; rank content opportunities; generate 2-3 differentiated comment drafts; add engagement queue and approval records; learn operator voice from explicitly supplied examples.

### Phase 3 — Relationship graph

Add relationship edges, buying-committee inference, account coverage, relationship-strength model, and graph visualization.

### Phase 4 — GTM command center

Unify accounts, people, signals, content, recommendations, approvals, and existing CRM previews into a recruiter-facing dashboard. Add evaluation cases for hallucinated relationships, unsupported role classifications, stale signals, duplicate people, and unsafe activation attempts.

### Phase 5 — Measured outcomes

Only after real operator usage, record actual approved actions and receipts. Report funnel/revenue metrics only when they are measured and attributable; otherwise show `not measured` rather than synthetic numbers.

## Portfolio positioning

> **Claude GTM Operating System** — an evidence-grounded GTM intelligence system that combines market signals, account intelligence, people and relationship context, content opportunities, deterministic scoring, Claude reasoning, and human-reviewed next-best actions.

The differentiator is not automated LinkedIn activity. It is **decision infrastructure for GTM**: deciding who matters, why now, what evidence supports the decision, and what action a human should take next.
