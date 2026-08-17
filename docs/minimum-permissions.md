# Minimum Permissions Reference

EM Radar only performs read operations against Jira and GitLab. It never creates, updates,
or deletes any data in those systems (REQ-NF-011). The token you provide needs only enough
access to read the projects, boards, sprints, issues, and merge requests you want to report on.

---

## GitLab

### Token type

Personal access token, sent as the `PRIVATE-TOKEN` request header.

### Minimum scope

| Scope | Why it is needed |
|---|---|
| `read_api` | Read access to the full GitLab API - projects, merge requests, notes, reviewer lists, pipeline status, and approval counts. No other scope is required. |

### How to create the token

1. Sign in to your GitLab instance.
2. Open your user menu (top-right avatar) and go to **Preferences** - **Access Tokens**
   (on older releases: **Edit profile** - **Access Tokens**).
3. Click **Add new token** (or **Generate a personal access token**).
4. Give it a descriptive name, for example `EM Radar`.
5. Set an expiry date if your organisation requires one.
6. Under **Select scopes**, tick only `read_api`. Do not select any write scopes.
7. Click **Create personal access token** and copy the value. Store it somewhere safe - it
   is shown only once.

In EM Radar, paste this value into the **Token** field on the GitLab connection form.

### What EM Radar reads via this scope

- `GET /api/v4/user` - verify the token is valid
- `GET /api/v4/personal_access_tokens/self` - read declared scopes for the connection test result
- `GET /api/v4/projects` - list projects the account can access (member repos only)
- `GET /api/v4/projects/:id/merge_requests` - list merge requests
- `GET /api/v4/projects/:id/merge_requests/:iid` - read diff stats
- `GET /api/v4/projects/:id/merge_requests/:iid/approvals` - count approvals
- `GET /api/v4/projects/:id/merge_requests/:iid/notes` - read review activity (system notes)
- `GET /api/v4/projects/:id/merge_requests/:iid/reviewers` - read reviewer assignments
- `GET /api/v4/merge_requests/:id` - resolve project/iid from a global MR id

All calls are read-only GET requests.

---

## Jira Cloud

### Authentication method

Your Atlassian account email address plus an API token, encoded as HTTP Basic auth. There
is no per-token scope selector in Jira Cloud; the API token inherits the account's project
permissions.

### Minimum permission

The Atlassian account that owns the token must have **Browse Projects** permission in every
Jira project you want to report on. This is the default permission for any project member;
no admin rights are needed.

The connector checks this permission at connection time via `GET /rest/api/2/mypermissions`
and shows the result in the connection test output.

> **Least-privilege note:** A Jira Cloud API token inherits the full permissions of the
> Atlassian account that created it. There is no per-token scope selector. If that account
> can edit issues, comment, or administer projects, the token can too. To make the credential
> genuinely read-only, use a dedicated account (or an existing one) whose Jira project roles
> are limited to Browse Projects with no edit, comment, or admin rights. EM Radar itself only
> issues GET requests and never writes to Jira, but a leaked token would carry whatever its
> owner account can do.

### How to create the token

1. Sign in to https://id.atlassian.com/manage-profile/security/api-tokens with the
   Atlassian account that can view the projects you want to report on.
2. Click **Create API token**.
3. Give it a label, for example `EM Radar`.
4. Click **Create** and copy the token.

In EM Radar, enter the account email in the **Auth Email** field and paste the token into
the **Token** field.

### What EM Radar reads

- `GET /rest/api/2/myself` - verify the token is valid
- `GET /rest/api/2/mypermissions` - check Browse Projects permission
- `GET /rest/api/2/project` - list projects
- `GET /rest/agile/1.0/board` - list boards for a project
- `GET /rest/agile/1.0/board/:id/sprint` - list sprints for a board
- `GET /rest/api/2/search/jql` (Cloud) or `GET /rest/api/2/search` (Server) - fetch issues
- `GET /rest/api/2/issue/:id` - fetch issue with changelog for transition history
- `GET /rest/api/2/issue/:id/changelog` - paginate changelog separately when needed
- `GET /rest/api/2/status` - load status categories

All calls are read-only GET requests.

---

## Jira Server / Data Center

### Authentication method

Personal Access Token (PAT), sent as a Bearer token in the `Authorization` header. Leave the
**Auth Email** field blank in EM Radar; the Server/DC connector uses the PAT alone.

### Minimum permission

The Jira account that owns the PAT must have **Browse Projects** permission in every project
you want to report on. No admin rights are needed. The Agile board and sprint endpoints are
accessible to any account with Browse Projects on the relevant project.

> **Least-privilege note:** A Jira Server/DC PAT inherits the full permissions of the user
> account that created it. There is no per-token scope selector. If that account can edit
> issues, comment, or administer projects, the PAT can too. To make the credential genuinely
> read-only, use a dedicated account (or an existing one) whose Jira project roles are limited
> to Browse Projects with no edit, comment, or admin rights. EM Radar itself only issues GET
> requests and never writes to Jira, but a leaked PAT would carry whatever its owner account
> can do.

### How to create the token

1. Sign in to your Jira Server or Data Center instance.
2. Open your user menu and go to **Profile** - **Personal Access Tokens**.
3. Click **Create token**, give it a name (for example `EM Radar`), and optionally set an
   expiry.
4. Click **Create** and copy the token.

In EM Radar, leave **Auth Email** blank and paste the PAT into the **Token** field.

### What EM Radar reads

The same endpoints as Jira Cloud (see above). The Agile REST API (`/rest/agile/1.0/...`)
is available when Jira Software is installed on the instance.

All calls are read-only GET requests.

---

## Read-only guarantee

EM Radar is designed to never write to Jira or GitLab (REQ-NF-011). The connectors issue
only GET requests. No issues are created, updated, or deleted. No merge requests are
commented on or modified.

This is a guarantee about EM Radar's behavior, not a property of every token type:

- **GitLab** - the `read_api` scope is enforced by GitLab itself. A `read_api` token cannot
  write regardless of what EM Radar or any other client does with it.
- **Jira Cloud and Jira Server/DC** - API tokens and PATs inherit the owning account's full
  permissions. EM Radar only issues GET requests, but the credential itself carries whatever
  the account can do. To make the token genuinely read-only at the credential level, restrict
  the owning account to Browse Projects only (see the least-privilege notes above).
