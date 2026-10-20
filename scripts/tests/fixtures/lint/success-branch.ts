import { z } from "zod"

export function isNumber(value: unknown): number {
  const result = z.number().safeParse(value)
  if (result.success) return result.data
  return 0
}
