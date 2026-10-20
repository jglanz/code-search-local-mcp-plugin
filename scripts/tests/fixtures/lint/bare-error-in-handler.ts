export function run(work: Promise<number>): Promise<number> {
  return work.catch(() => {
    throw new Error("work failed")
  })
}
