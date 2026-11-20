# RC27 Account Authentication & User Management

## Decision

DAEP Web UI uses account + password authentication. API and MCP integrations continue to use bearer tokens as machine credentials.

### Identity layers

1. Platform account
   - username
   - password
   - account status
   - platform role: system admin or member
2. Project membership
   - project role: owner / manager / reviewer / member
   - work function: developer / tester / product / architect / other
3. Local Agent identity
   - MCP/API credential
   - registered to a project member
   - independently running on the member's workstation

The same person can belong to multiple projects and hold different project roles in each project.

## Web login

- POST /api/v1/auth/login accepts username + password.
- Passwords are stored as PBKDF2-SHA256 salted hashes.
- The login response returns a bearer credential for API calls; the Web UI does not expose or ask the user to paste a token.
- POST /api/v1/auth/change-password lets an authenticated member change their password.
- API/MCP bearer tokens remain available for machine-to-machine integrations and are not the Web login UX.

## User provisioning

System administrators use 用户管理 to create platform member accounts.

Required fields:
- name
- username
- initial password

Project roles are deliberately not assigned during platform account creation. Project managers assign a user to a project and choose the project role and work function from that project's member management surface.

## Bootstrap administrator

DAEP_BOOTSTRAP_ADMIN_PASSWORD can seed the existing bootstrap administrator's password on first initialization when no password hash exists. The bootstrap administrator remains the only platform admin identity created by bootstrap.

## Migration

Existing RC member records retain their API token credentials. Username/password columns are additive. Existing accounts receive a deterministic username fallback when possible; administrators should set/confirm production usernames and passwords before disabling token-only Web access.

## Acceptance impact

This change invalidates any prior browser evidence that used a Token field on the Web login page. Browser acceptance must be rerun with:
- system administrator account/password
- project manager account/password
- product/developer/tester/reviewer project memberships
- unauthorized project and user-management controls
