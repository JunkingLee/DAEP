# RC26 Stage 8 — Two-member Agent delivery acceptance E2E

## Scope

This stage adds an API-level end-to-end acceptance test for the complete DAEP governance path across two independently authenticated project members, each operating a separately registered local MCP-compatible Agent.

DAEP coordinates project work and evidence. The test does not create, host, start, stop, or control either Agent runtime.

## Covered flow

1. Create a project, coordinator, two member identities, a requirement with acceptance criteria, and a parent task.
2. Register two distinct local Agents under their respective member identities, with separate capabilities and MCP protocol declarations.
3. Create two work packages under the parent task and route each package to its corresponding member/Agent.
4. Send a project-work message from member A to member B; verify inbox delivery and explicit ACK from member B.
5. Submit a distinct artifact and COMPLETE work result from each member. Both child tasks enter REVIEW.
6. Verify that parent approval is blocked while child work packages remain unreviewed.
7. Approve each child task, then verify the aggregated parent work summary and cross-member work timeline, including both artifacts and the acknowledged message.
8. Attach the parent delivery bundle, approve the parent task, and verify the requirement acceptance report becomes ready.
9. Explicitly verify every acceptance criterion and approve the requirement; verify the acceptance audit event.

## Acceptance guarantees exercised

- Member-scoped authentication for Agent work and messaging.
- Separate Agent identity by member and Agent name.
- Durable message inbox and explicit acknowledgement.
- Artifact-backed work results.
- Parent completion gate waits for all child work packages to be approved.
- Cross-member trace joins work packages, messages, ACK state, and artifacts.
- Requirement acceptance requires completed task delivery evidence and explicit criterion verification.
- Final decision is auditable.

## Test boundary

This is a deterministic FastAPI integration test using the repository test database. It validates the server-side API contract and workflow state transitions. It does **not** claim to validate real MCP Host interoperability, background wake-up of sleeping local Agents, browser rendering, multiple physical computers, network partition recovery, or a production backup/restore drill. Those remain separate release-candidate validation activities.
