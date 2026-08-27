import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SchemaForm } from "@/components/SchemaForm"
import type { JsonSchema } from "@/lib/jsonSchema"

afterEach(cleanup)

const jiraSchema: JsonSchema = {
  type: "object",
  $defs: {
    JiraFieldMappingConfig: {
      type: "object",
      title: "JiraFieldMappingConfig",
      properties: {
        story_points: { type: "string", title: "Story Points", default: "customfield_10016" },
        epic_link: { type: "string", title: "Epic Link", default: "customfield_10014" },
        blocked_label: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Blocked Label",
          default: "blocked",
        },
      },
    },
  },
  properties: {
    base_url: { type: "string", title: "Base Url" },
    token: { type: "string", title: "Token", writeOnly: true },
    field_mapping: { $ref: "#/$defs/JiraFieldMappingConfig" },
  },
  required: ["base_url", "token"],
}

const gitlabSchema: JsonSchema = {
  type: "object",
  properties: {
    base_url: { type: "string", title: "Base Url" },
    token: { type: "string", title: "Token", writeOnly: true },
  },
  required: ["base_url", "token"],
}

describe("SchemaForm — nested object via $ref", () => {
  it("renders sub-fields for a $ref object property instead of a text input", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={jiraSchema}
        values={{}}
      />,
    )

    // fieldLabel strips the trailing "Config" and splits PascalCase
    expect(screen.getByRole("group", { name: "Jira Field Mapping" })).toBeInTheDocument()
    expect(screen.getByLabelText("Story Points")).toBeInTheDocument()
    expect(screen.getByLabelText("Epic Link")).toBeInTheDocument()
    expect(screen.getByLabelText("Blocked Label")).toBeInTheDocument()
  })

  it("pre-fills sub-fields with schema defaults when no value is set", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={jiraSchema}
        values={{}}
      />,
    )

    expect((screen.getByLabelText("Story Points") as HTMLInputElement).value).toBe(
      "customfield_10016",
    )
    expect((screen.getByLabelText("Epic Link") as HTMLInputElement).value).toBe("customfield_10014")
  })

  it("pre-fills sub-fields with existing nested values when editing", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={jiraSchema}
        values={{ field_mapping: { story_points: "customfield_99999", epic_link: "cf_42" } }}
      />,
    )

    expect((screen.getByLabelText("Story Points") as HTMLInputElement).value).toBe(
      "customfield_99999",
    )
    expect((screen.getByLabelText("Epic Link") as HTMLInputElement).value).toBe("cf_42")
  })

  it("calls onChange with a nested object when a sub-field changes", () => {
    const onChange = vi.fn()
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={onChange}
        schema={jiraSchema}
        values={{ field_mapping: { story_points: "customfield_10016", epic_link: "customfield_10014" } }}
      />,
    )

    fireEvent.change(screen.getByLabelText("Story Points"), {
      target: { value: "customfield_99999" },
    })

    expect(onChange).toHaveBeenCalledWith("field_mapping", {
      story_points: "customfield_99999",
      epic_link: "customfield_10014",
    })
  })

  it("renders the token as a password input (write-only) inside the Jira form", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={jiraSchema}
        values={{}}
      />,
    )

    const token = screen.getByLabelText("Token") as HTMLInputElement
    expect(token.type).toBe("password")
  })

  it("does not render a raw text input for the field_mapping key", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={jiraSchema}
        values={{}}
      />,
    )

    const input = screen.queryByRole("textbox", { name: "Jira Field Mapping" })
    expect(input).not.toBeInTheDocument()
  })
})

describe("SchemaForm — flat GitLab schema is unaffected", () => {
  it("renders base_url and token as flat inputs without any fieldset", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{ base_url: "https://gitlab.example.com" }}
      />,
    )

    expect(screen.getByLabelText("Base Url")).toBeInTheDocument()
    expect(screen.getByLabelText("Token")).toBeInTheDocument()
    expect(screen.queryByRole("group")).not.toBeInTheDocument()
  })

  it("calls onChange with the flat key when a top-level field changes", () => {
    const onChange = vi.fn()
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={onChange}
        schema={gitlabSchema}
        values={{ base_url: "https://gitlab.example.com" }}
      />,
    )

    fireEvent.change(screen.getByLabelText("Base Url"), {
      target: { value: "https://new.example.com" },
    })

    expect(onChange).toHaveBeenCalledWith("base_url", "https://new.example.com")
  })
})

describe("SchemaForm — allOf single-branch resolution", () => {
  it("renders a text input when a property is wrapped in a single-branch allOf", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        url: { allOf: [{ type: "string", title: "URL" }] },
      },
    }

    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={schema}
        values={{}}
      />,
    )

    expect(screen.getByLabelText("URL")).toBeInTheDocument()
  })

  it("renders a password input when writeOnly is on the outer allOf wrapper", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        token: { writeOnly: true, allOf: [{ type: "string", title: "Token" }] },
      },
    }

    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={schema}
        values={{}}
      />,
    )

    expect(screen.getByLabelText("Token")).toHaveAttribute("type", "password")
  })
})

// ---------------------------------------------------------------------------
// Required-field accessibility: required / aria-required on inputs (AUDIT-12)
// ---------------------------------------------------------------------------

describe("SchemaForm — required field attributes", () => {
  it("a required text input has the required attribute", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{}}
      />,
    )

    expect(screen.getByLabelText("Base Url")).toHaveAttribute("required")
    expect(screen.getByLabelText("Token")).toHaveAttribute("required")
  })

  it("a required text input has aria-required set to true", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{}}
      />,
    )

    expect(screen.getByLabelText("Base Url")).toHaveAttribute("aria-required", "true")
    expect(screen.getByLabelText("Token")).toHaveAttribute("aria-required", "true")
  })

  it("a non-required field does not have the required attribute", () => {
    const schema: JsonSchema = {
      type: "object",
      properties: {
        notes: { type: "string", title: "Notes" },
      },
    }

    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={schema}
        values={{}}
      />,
    )

    expect(screen.getByLabelText("Notes")).not.toHaveAttribute("required")
  })

  it("the required * marker is aria-hidden; aria-required on the input is the a11y signal", () => {
    const { container } = render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{}}
      />,
    )

    // The visual * must be aria-hidden (purely decorative; the input carries aria-required).
    const stars = Array.from(container.querySelectorAll('[aria-hidden="true"]')).filter(
      (el) => el.textContent === "*",
    )
    expect(stars.length).toBeGreaterThan(0)

    // No free-floating sr-only "required" span — would cause a double announcement.
    expect(screen.queryByText("required")).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Secret field label copy (M8.7-01)
// ---------------------------------------------------------------------------

describe("SchemaForm — secret field label copy", () => {
  it("shows 'Stored securely, not shown again' for a secret field in add mode", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{}}
      />,
    )

    expect(screen.getByText("Stored securely, not shown again")).toBeInTheDocument()
  })

  it("shows 'Leave blank to keep current token' for a secret field in edit mode (exemptSecrets)", () => {
    render(
      <SchemaForm
        exemptSecrets
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{ token: "" }}
      />,
    )

    expect(screen.getByText("Leave blank to keep current token")).toBeInTheDocument()
  })

  it("does not render the literal text 'write-only' anywhere", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{}}
      />,
    )

    expect(screen.queryByText(/write-only/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// exemptSecrets: secret fields are non-required in edit mode
// ---------------------------------------------------------------------------

describe("SchemaForm — exemptSecrets prop", () => {
  it("without exemptSecrets, a writeOnly (secret) field has required and aria-required", () => {
    render(
      <SchemaForm
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{}}
      />,
    )

    const token = screen.getByLabelText("Token")
    expect(token).toHaveAttribute("required")
    expect(token).toHaveAttribute("aria-required", "true")
  })

  it("with exemptSecrets, a writeOnly (secret) field does not have required or aria-required", () => {
    render(
      <SchemaForm
        exemptSecrets
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{ token: "" }}
      />,
    )

    const token = screen.getByLabelText("Token")
    expect(token).not.toHaveAttribute("required")
    expect(token).not.toHaveAttribute("aria-required", "true")
  })

  it("with exemptSecrets, a non-secret required field still has required and aria-required", () => {
    render(
      <SchemaForm
        exemptSecrets
        idPrefix="conn"
        onChange={() => undefined}
        schema={gitlabSchema}
        values={{}}
      />,
    )

    const baseUrl = screen.getByLabelText("Base Url")
    expect(baseUrl).toHaveAttribute("required")
    expect(baseUrl).toHaveAttribute("aria-required", "true")
  })
})
