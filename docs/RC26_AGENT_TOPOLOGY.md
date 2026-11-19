# RC26 Stage 1 — Local Agent Collaboration Topology

## Purpose

Provide project managers and members with a read-only view of local Agents registered by project members and the DAEP work packages associated with those Agent identities.

## Data sources

The view combines the authenticated project-scoped `GET /api/v1/projects/{pid}/agents` registry with the existing project work-health API. Agent identity is matched by both `agent_name` and `member_id`, not by display name alone. The view shows presence state, last heartbeat, declared protocols/capabilities, assigned active work packages, progress, risk state and unresolved blockers. Work packages without a matching Agent registration are called out separately.

## Runtime boundary

Agent status is only the registry's last reported presence with the existing 120-second freshness rule. It is not proof that a host process is running, and it does not allow DAEP to start, stop, execute, inspect or wake a local Agent Runtime. Each member continues to operate their own local MCP-compatible Agent/Host.

## Verification

Static tests verify the topology panel, project-scoped registry wiring and member+Agent matching. CI also extracts the dashboard inline JavaScript and runs `node --check`. Browser rendering and real multi-host presence behavior still require target-environment acceptance.
