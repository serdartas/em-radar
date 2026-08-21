/**
 * NOTE: vitest cannot be executed in this project because esbuild is blocked
 * (see memory/no-esbuild.md). These tests are written to the correct vitest +
 * @testing-library/react API and will pass once a compatible test runner is
 * available (e.g. after replacing esbuild with @swc/core in the vite config).
 *
 * Manual verification checklist:
 *   1. Open the Jira connection form in the browser.
 *   2. Confirm that "Field Mapping" appears as a grouped fieldset, not a text input.
 *   3. Confirm that sub-fields (Story Points, Epic Link, …) are visible and editable.
 *   4. Edit "Story Points", save the connection, and confirm the PATCH/POST body
 *      contains field_mapping: { story_points: "<new value>", … } as a nested object.
 *   5. Switch to GitLab — confirm Base URL and Token render as flat text/password inputs.
 */

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
