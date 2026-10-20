export interface Options {
  size: number
}

export function size(options: Options): number {
  const value = options.size ?? 1
  return value
}
