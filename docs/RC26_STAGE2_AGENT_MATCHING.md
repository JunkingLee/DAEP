# RC26 Stage 2 — Explainable local Agent matching

## Purpose

Help a project member identify which registered workstation Agent is a plausible collaboration target for a task's declared capability needs. Matching is project-scoped and advisory.

## API

`GET /api/v1/projects/{project_id}/agent-matches?required_capabilities=python,testing&protocol=mcp`

- Requires project membership; results never cross project boundaries.
- `required_capabilities` is an optional comma-separated list (maximum 50 distinct values, each at most 120 characters).
- `protocol` defaults to `mcp` and must contain 1–40 characters.
- Matching is case-insensitive. Duplicate requested capabilities are removed.
- Results include the member and Agent identity, advertised capabilities/protocols, matched and missing capabilities, presence status, last heartbeat, availability reason, match score, protocol match and eligibility.
- Results sort eligible candidates first, followed by better capability coverage and stable member/Agent names.
- An Agent is eligible only when all requested capabilities and the requested protocol match and its registration is recently heartbeating (120-second freshness window) with status `AVAILABLE`.
- `BUSY`, stale and offline Agents remain visible for transparency but are not eligible.

## Safety and product boundary

This API is recommendation-only. It does not assign a task, create a delegation, send a message, invoke an MCP method, or start/wake/inspect/control an Agent Runtime. A human must decide whether to create a delegation using the existing explicit offer-and-accept workflow. Capability declarations are self-reported metadata, not verified proof of competence.

## Verification

Automated API tests cover exact and partial capability matches, presence/availability eligibility, project membership isolation, input bounds, and the absence of implicit task assignment. CI checks remain necessary before considering the stage complete.
