import type { Config } from "jest"

const config: Config = {
  // Bounded concurrency: each worker runs suites under --experimental-vm-modules,
  // whose module registries are not reclaimed between files.
  maxWorkers: 2,
  // Recycle a worker whose heap stays above this size after a file.
  workerIdleMemoryLimit: "2GB",
  // Multi-project Jest honours this ROOT timeout, not per-project values.
  testTimeout: 60_000,
  // The Python package (packages/code-search-local) is tested by hatch, never by jest.
  projects: [
    "packages/code-search-local-api",
    "packages/code-search-local-webapp"
  ]
}

export default config
