export function readField(value: unknown, key: string): unknown {
  return typeof value === "object" && value !== null && key in value
    ? Reflect.get(value, key)
    : undefined;
}

export function optionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

export function optionalNumber(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

export function arrayLength(value: unknown): number | undefined {
  return Array.isArray(value) ? value.length : undefined;
}

export function nonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}
