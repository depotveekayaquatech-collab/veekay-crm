/** Deep snake_case -> camelCase for API payloads (keys only; values untouched). */
export function camelize<T>(input: unknown): T {
  if (Array.isArray(input)) return input.map((x) => camelize(x)) as T;
  if (input && typeof input === "object") {
    return Object.fromEntries(
      Object.entries(input as Record<string, unknown>).map(([k, v]) => [
        k.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase()),
        camelize(v),
      ]),
    ) as T;
  }
  return input as T;
}
