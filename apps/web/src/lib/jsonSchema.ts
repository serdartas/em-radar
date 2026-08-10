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
  $ref?: string
  allOf?: JsonSchemaProperty[]
  anyOf?: JsonSchemaProperty[]
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
}

export interface JsonSchema {
  type?: JsonSchemaType
  properties?: Record<string, JsonSchemaProperty>
  required?: string[]
  additionalProperties?: boolean
  $defs?: Record<string, JsonSchemaProperty>
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
  if (property.anyOf) {
    const nonNull = property.anyOf.find((candidate) => candidate.type !== "null")
    if (nonNull?.type !== undefined) {
      return Array.isArray(nonNull.type)
        ? (nonNull.type.find((t) => t !== "null") ?? "string")
        : nonNull.type
    }
  }
  const type = Array.isArray(property.type)
    ? property.type.find((candidate) => candidate !== "null")
    : property.type
  return type ?? "string"
}

export function resolveProperty(
  property: JsonSchemaProperty,
  defs: Record<string, JsonSchemaProperty>,
): JsonSchemaProperty {
  if (property.$ref !== undefined) {
    const key = property.$ref.replace(/^#\/\$defs\//, "")
    // Merge reference-node annotations (e.g. writeOnly added by _schema_with_secret_flags)
    // into the resolved definition so credential fields render as password inputs.
    const merged = { ...(defs[key] ?? {}), ...property }
    delete merged.$ref
    return merged
  }

  if (property.allOf?.length === 1) {
    return resolveProperty(property.allOf[0], defs)
  }

  return property
}
