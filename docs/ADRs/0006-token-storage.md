# ADR-0006: Token storage — SQLite with masking

- **Status:** Accepted
- **Date:** 2026-06-01
- **Deciders:** Serdar Tas
- **Related:** [04-tech-stack.md](../04-tech-stack.md), [ADR-0002](./0002-default-database.md), [02-requirements.md](../02-requirements.md) (REQ-NF-003)

## Context

EM Radar stores Jira and GitLab personal access tokens locally so it can fetch source data. The MVP runs in Docker on a single EM's machine.

REQ-NF-003 requires:

- Tokens masked in UI.
- Tokens never logged.
- Tokens never included in config exports.
- Documentation recommends read-only tokens where possible.

We must pick a storage mechanism that satisfies these requirements without adding setup friction that would scare off non-DBA EMs.

## Decision

Store tokens in the **local SQLite database** alongside other connector config. Apply UI masking, log scrubbing, and export exclusion at the application layer. Defer stronger at-rest protection (encryption, OS keychain, secret managers) to a later phase.

## Alternatives considered

### OS keyring (via Python `keyring` library)
- **Strengths:** Uses platform-native secret stores (macOS Keychain, Windows Credential Locker, Linux Secret Service). Strong at-rest protection. Tokens never sit in a plain file on disk.
- **Weaknesses:**
  - Docker containers don't naturally access the host's keychain. Requires volume mounts, D-Bus socket forwarding, or moving the keyring inside the container (which then defeats the purpose).
  - Inconsistent experience across host OSes. Linux Secret Service requires a running session bus.
  - Adds setup steps that scare off the non-DBA EM persona.
  - Backup/restore of the EM Radar instance no longer means "copy one volume". It now also depends on host keyring state.
- **Verdict:** Right answer for a desktop-native (non-Docker) wrapper. Wrong answer for the local-Docker MVP.

### Encrypted SQLite (SQLCipher) or encrypted token column (age / Fernet)
- **Strengths:** At-rest encryption while keeping single-file simplicity.
- **Weaknesses:** Needs a master password or master key UX. Where is the key stored? If it's on disk next to the database, encryption is theater. If the user types a password, every restart requires re-entry, breaking unattended scheduled runs and complicating Docker startup.
- **Verdict:** Adds complexity disproportionate to the actual threat model for a single-user local app.

### Environment variables / Docker secrets
- **Strengths:** Tokens never persisted to disk by the app.
- **Weaknesses:** Reconfiguring a connection means restarting the container. UI-driven token management (the whole point of the setup page) becomes impossible. EMs would have to edit Docker config.
- **Verdict:** Loses on usability for the target persona.

### SQLite (chosen)
- **Strengths:**
  - Zero additional moving parts. Already our database (see [ADR-0002](./0002-default-database.md)).
  - Tokens managed through the UI like any other config.
  - Single file = single backup story = single delete story.
  - Works identically on every host OS.
- **Weaknesses:**
  - Tokens are at rest in a SQLite file on disk. Mitigated, not eliminated.

## Threat model

Realistic threats for the MVP local-first deployment:

| Threat | Likelihood | Mitigation |
|---|---|---|
| Casual UI screenshot leaks token | Medium | UI masking |
| Token ends up in shipped logs | Medium | Log scrubbing, no Authorization header logging |
| Token exported in a shared config pack | High if not handled | Exports exclude credentials |
| Attacker with full read access to disk | Low (local laptop) and game-over regardless | Out of scope (same attacker could read keyring too if they have user-level access) |
| Stolen unlocked laptop | Low–medium | Read-only token recommendation limits blast radius |

The dominant mitigation is **recommending read-only tokens**. Even if compromised, an attacker cannot modify Jira/GitLab through them (also enforced by REQ-NF-011).

## Consequences

### Positive
- Simplest possible MVP path.
- Fully self-contained in the Docker volume.
- Identical behavior across macOS / Windows / Linux.
- UI-managed connections. No host-OS coupling.

### Negative
- Tokens are at rest in a plaintext-readable file (within the local volume). An attacker with disk-level access to the user's machine can read them.
- We rely on application-layer discipline (masking, log scrubbing, export exclusion). Easy to regress without tests.

## Mitigations

- Mask tokens in all UI surfaces (show last 4 chars max).
- Never log raw tokens or Authorization headers.
- Exclude tokens from YAML exports. Exporter must round-trip exclude credential fields.
- Document the recommendation to use **read-only** Jira/GitLab tokens.
- Provide a clear "delete this connection" action that removes the token row.
- Add automated tests that:
  - Exports do not contain known token values from fixtures.
  - Log output does not contain known token values from fixtures.

## Revisit when

- We ship a desktop (non-Docker) wrapper where OS keyring access is natural and friction-free.
- We add an enterprise/multi-user deployment that needs integration with a real secret manager (Vault, AWS Secrets Manager, etc.).
- A realistic threat model emerges where at-rest disk encryption is the missing control.
