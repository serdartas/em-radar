export type JsonSchemaType =
  | "array"
  | "boolean"
  | "integer"
  | "null"
  | "number"
  | "object"
  | "string"

export interface JsonSchemaProperty {
  type?: JsonSchemaType | JsonSchemaType[]
  title?: string
  description?: string
  default?: unknown
  enum?: unknown[]
  writeOnly?: boolean
  format?: string
  items?: JsonSchemaProperty
}

export interface JsonSchema {
  type?: JsonSchemaType
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
  additionalProperties?: boolean
}

export function fieldLabel(key: string, property: JsonSchemaProperty): string {
  if (property.title) {
    return property.title
  }
  return key
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export function isSecret(property: JsonSchemaProperty): boolean {
  return property.writeOnly === true
}

export function schemaType(property: JsonSchemaProperty): JsonSchemaType {
  const type = Array.isArray(property.type)
    ? property.type.find((candidate) => candidate !== "null")
    : property.type
  return type ?? "string"
}
