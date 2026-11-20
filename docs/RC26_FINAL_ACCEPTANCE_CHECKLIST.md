# DAEP RC26 Final Product Acceptance Checklist

## Purpose
This checklist separates automated release evidence from the remaining real-environment acceptance work. RC26 is a release candidate; completion of CI alone is not a GA declaration.

## A. Automated acceptance — PASS
- [x] Python 3.11/3.12/3.13 test matrix green
- [x] PostgreSQL migration/RLS checks green
- [x] Production Compose verification green
- [x] Container build verification green
- [x] Dashboard JavaScript checks green
- [x] Role-aware workbench UI checks present
- [x] Full role delivery E2E covered by API integration tests
- [x] Two-member Agent delivery E2E covered at server/API level
- [x] Outbox recovery and concurrent claim safety covered
- [x] Idempotency/state-transition race coverage
- [x] Project role/work-function isolation coverage
- [x] Workflow and configurable gate enforcement coverage

## B. Real browser acceptance — REQUIRED
Run against a deployed RC instance:
- [ ] System Admin can create/manage projects and platform governance
- [ ] Project Manager can manage multiple projects and switch project context
- [ ] Product role sees product-oriented workbench and requirement flow
- [ ] Developer sees assigned implementation work and workflow transitions
- [ ] Tester sees test/acceptance workbench, evidence controls and acceptance report
- [ ] Reviewer can review tasks and requirements
- [ ] Unauthorized controls are hidden or rejected
- [ ] Workflow designer renders configured stages correctly
- [ ] System gates are visibly locked
- [ ] Custom gates can be configured and enforced
- [ ] Empty/loading/error states are usable
- [ ] Refresh and project switching preserve correct context
- [ ] Mobile/narrow viewport remains usable

## C. Real deployment acceptance — REQUIRED
- [ ] Deploy production Compose in a clean environment
- [ ] Verify API and browser access against PostgreSQL
- [ ] Execute an actual backup
- [ ] Restore into a separately provisioned empty PostgreSQL target
- [ ] Run restored-database verification script
- [ ] Verify application behavior after restore
- [ ] Record restore duration and recovery observations
- [ ] Confirm secrets/configuration handling
- [ ] Confirm external ingress/TLS and operational monitoring

## D. Real Agent interoperability — REQUIRED
- [ ] Register two independently running local MCP-compatible Agents
- [ ] Verify heartbeat/presence from separate hosts
- [ ] Execute two-member work-package collaboration using real Agents
- [ ] Verify durable message delivery and ACK
- [ ] Verify artifact/result submission from both Agents
- [ ] Verify manual reassignment to a different registered Agent
- [ ] Document that DAEP does not own or wake local Agent Runtime processes

## E. Release decision
RC26 may be considered code-complete / RC-ready when A is green.

RC26 must not be called GA-ready until B, C and D have been executed and accepted by the release owner.

## Current status
- Code-level acceptance: PASS
- CI acceptance: PASS
- Browser acceptance: NOT YET EXECUTED
- Production restore drill: NOT YET EXECUTED
- Real multi-host MCP interoperability: NOT YET EXECUTED
- Main merge: NOT authorized
