import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"

import { GitLabHelpPage } from "@/pages/GitLabHelpPage"

afterEach(cleanup)

describe("GitLabHelpPage", () => {
  it("renders the page heading", () => {
    render(
      <MemoryRouter>
        <GitLabHelpPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole("heading", { name: /Connecting to GitLab/ })).toBeInTheDocument()
  })

  it("links out to the official GitLab docs", () => {
    render(
      <MemoryRouter>
        <GitLabHelpPage />
      </MemoryRouter>,
    )

    const docsLink = screen.getByRole("link", { name: /Personal access tokens/ })
    expect(docsLink).toHaveAttribute(
      "href",
      "https://docs.gitlab.com/user/profile/personal_access_tokens/",
    )
  })

  it("links back to the connections page", () => {
    render(
      <MemoryRouter>
        <GitLabHelpPage />
      </MemoryRouter>,
    )

    const backLink = screen.getByRole("link", { name: /Back to Source Connections/ })
    expect(backLink).toHaveAttribute("href", "/connections")
  })

  it("mentions the read_api scope", () => {
    render(
      <MemoryRouter>
        <GitLabHelpPage />
      </MemoryRouter>,
    )

    expect(screen.getAllByText("read_api").length).toBeGreaterThan(0)
  })
})
