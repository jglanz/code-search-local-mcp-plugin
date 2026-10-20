import { asOption } from "@3fv/prelude-ts"

export async function load(read: () => Promise<number>): Promise<number> {
  return asOption(await read()).getOrElse(0)
}
