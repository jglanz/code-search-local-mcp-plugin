export function run(work: () => number): number {
  try {
    return work()
  } catch (err) {
    void err
    throw new Error("work failed")
  }
}
