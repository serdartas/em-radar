import { ArrowLeft, ExternalLink } from "lucide-react"
import { Link } from "react-router-dom"

import { Card, CardContent, CardHeader } from "@/components/ui/card"

const ATLASSIAN_CLOUD_DOCS =
  "https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/"
const ATLASSIAN_SERVER_DOCS =
  "https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html"

export function JiraHelpPage() {
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
          Connecting to Jira
        </h1>
        <p className="max-w-2xl text-slate-600">
          EM Radar reads from Jira using a Base URL and an API token. How you obtain the token
          depends on whether you run Jira Cloud or Jira Server / Data Center.
        </p>
      </header>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Base URL</h2>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-600">
          <p>
            The Base URL is the root address of your Jira instance. Open Jira in your browser and
            copy the address up to the domain.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              Jira Cloud:{" "}
              <code className="rounded bg-slate-100 px-1">https://your-org.atlassian.net</code>
            </li>
            <li>Jira Server / Data Center: your self-hosted address, e.g. https://jira.example.com</li>
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Jira Cloud - API token</h2>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-600">
          <ol className="list-decimal space-y-1 pl-5">
            <li>Sign in to your Atlassian account and open the API tokens page.</li>
            <li>Create a token, give it a label, and copy the generated value.</li>
            <li>
              In EM Radar, enter your Atlassian account email and paste the token into the Token
              field.
            </li>
          </ol>
          <a
            className="inline-flex items-center gap-1 font-medium text-blue-700 underline"
            href={ATLASSIAN_CLOUD_DOCS}
            rel="noreferrer"
            target="_blank"
          >
            Atlassian docs: Manage API tokens
            <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
          </a>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Jira Server / Data Center - Personal Access Token</h2>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-600">
          <ol className="list-decimal space-y-1 pl-5">
            <li>Open your Jira profile and go to Personal Access Tokens.</li>
            <li>Create a token with read access to the projects and boards you report on.</li>
            <li>Copy the token and paste it into the Token field. The email field is not required.</li>
          </ol>
          <a
            className="inline-flex items-center gap-1 font-medium text-blue-700 underline"
            href={ATLASSIAN_SERVER_DOCS}
            rel="noreferrer"
            target="_blank"
          >
            Atlassian docs: Using Personal Access Tokens
            <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
          </a>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Minimum permissions</h2>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-slate-600">
          <p>
            The account that owns the token needs only <strong>Browse Projects</strong>{" "}
            permission in the Jira projects you report on. No admin rights are needed.
          </p>
          <p>
            EM Radar never writes to Jira. No issues are created, updated, or deleted. The
            connector issues only read-only requests.
          </p>
          <p>
            Jira tokens carry no per-token scope selector - they inherit the owning
            account&apos;s full permissions. For least privilege, use a dedicated account
            (or an existing one) limited to Browse Projects with no edit, comment, or admin
            rights. A token from an account with broader permissions carries those permissions
            too, even though EM Radar never uses them.
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
