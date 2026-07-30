import { cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it } from "vitest"

import { JiraHelpPage } from "@/pages/JiraHelpPage"

afterEach(cleanup)

describe("JiraHelpPage", () => {
  it("links out to the official Atlassian docs", () => {
    render(
      <MemoryRouter>
        <JiraHelpPage />
      </MemoryRouter>,
    )

    const cloud = screen.getByRole("link", { name: /Manage API tokens/ })
    expect(cloud).toHaveAttribute(
      "href",
      "https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/",
    )

    const server = screen.getByRole("link", { name: /Personal Access Tokens/ })
    expect(server).toHaveAttribute(
      "href",
      "https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html",
    )
  })
})
