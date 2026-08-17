import { ArrowLeft, ExternalLink } from "lucide-react"
import { Link } from "react-router-dom"

import { Card, CardContent, CardHeader } from "@/components/ui/card"

const GITLAB_PAT_DOCS =
  "https://docs.gitlab.com/user/profile/personal_access_tokens/"

export function GitLabHelpPage() {
  return (
    <section aria-labelledby="page-title" className="space-y-8">
      <header className="space-y-2">
        <Link
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-foreground"
          to="/connections"
        >
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          Back to Source Connections
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight" id="page-title">
          Connecting to GitLab
        </h1>
        <p className="max-w-2xl text-slate-600">
          EM Radar reads from GitLab using a Base URL and a personal access token. The token
          needs only the <code className="rounded bg-slate-100 px-1">read_api</code> scope -
          no write access is required or granted.
        </p>
      </header>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Base URL</h2>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-600">
          <p>
            The Base URL is the root address of your GitLab instance. Open GitLab in your
            browser and copy the address up to the domain.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              GitLab SaaS:{" "}
              <code className="rounded bg-slate-100 px-1">https://gitlab.com</code>
            </li>
            <li>
              Self-managed: your self-hosted address, e.g.{" "}
              <code className="rounded bg-slate-100 px-1">https://gitlab.example.com</code>
            </li>
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">
            Personal access token - minimum scope <code className="rounded bg-slate-100 px-1 text-base font-normal">read_api</code>
          </h2>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-600">
          <p>
            EM Radar only reads data from GitLab. The{" "}
            <code className="rounded bg-slate-100 px-1">read_api</code> scope is the only
            scope needed. Do not add any write scopes.
          </p>
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              Sign in to GitLab and open your user menu (top-right avatar).
            </li>
            <li>
              Go to <strong>Preferences</strong> - <strong>Access Tokens</strong> (on older
              releases: <strong>Edit profile</strong> - <strong>Access Tokens</strong>).
            </li>
            <li>Click <strong>Add new token</strong>.</li>
            <li>Give the token a name, for example <em>EM Radar</em>, and set an optional expiry.</li>
            <li>
              Under <strong>Select scopes</strong>, tick only{" "}
              <code className="rounded bg-slate-100 px-1">read_api</code>. Do not select any
              write scopes.
            </li>
            <li>
              Click <strong>Create personal access token</strong> and copy the value. It is
              shown only once.
            </li>
            <li>In EM Radar, paste the token into the Token field.</li>
          </ol>
          <a
            className="inline-flex items-center gap-1 font-medium text-blue-700 underline"
            href={GITLAB_PAT_DOCS}
            rel="noreferrer"
            target="_blank"
          >
            GitLab docs: Personal access tokens
            <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
          </a>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Read-only guarantee</h2>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-600">
          <p>
            EM Radar never writes to GitLab. No merge requests are created, commented on, or
            modified. The connector issues only GET requests to the GitLab API. A{" "}
            <code className="rounded bg-slate-100 px-1">read_api</code>-only token enforces
            this at the token level.
          </p>
        </CardContent>
      </Card>

      <p className="text-sm text-slate-500">
        Tokens are stored locally on your machine and shown masked in EM Radar. They are never
        logged or included in exported configurations.
      </p>
    </section>
  )
}
