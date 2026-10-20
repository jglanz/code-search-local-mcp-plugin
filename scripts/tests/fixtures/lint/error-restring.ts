export function wrap(err: Error): Error {
  return new Error(`failed: ${err.message}`)
}
