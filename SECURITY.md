# Security Policy

EM Radar is a local-first tool that handles sensitive data: personal access tokens for Jira
and GitLab, and normalized data from your company's source systems. We take security
reports seriously.

## Supported versions

EM Radar is pre-alpha. Until a `v0.1.0` release is tagged, only the latest `main` is
supported. After the first release, this section will list the supported versions.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues, discussions, or
pull requests.**

Instead, use **GitHub's private vulnerability reporting**:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Provide a description, steps to reproduce, affected version/commit, and impact.

If you cannot use GitHub's private reporting, contact the maintainer directly
(see the repository owner's profile).

### What to expect

- We will acknowledge your report as soon as we can.
- We will investigate and keep you informed of progress.
- We will credit you in the release notes when the fix ships, unless you prefer to remain
  anonymous.

## Scope and handling notes

Areas where security reports are especially valuable, given EM Radar's design:

- **Token handling.** Tokens must never be logged, returned in API responses, included in
  YAML exports, or rendered unmasked in the UI. Any path that leaks a token is in scope.
- **Config import.** Imported signal-pack YAML must be declarative and schema-validated;
  any way to achieve code execution via import is in scope.
- **Local data exposure.** Unintended exposure of the local SQLite database, cached source
  data, or generated reports beyond the local machine.
- **Dependency vulnerabilities** with a practical impact on EM Radar.

Thank you for helping keep EM Radar and its users safe.
