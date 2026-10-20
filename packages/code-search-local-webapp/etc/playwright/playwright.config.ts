import path from "node:path"

import { defineConfig, devices } from "@playwright/test"

/** This package's root. */
const PackagePath = path.resolve(import.meta.dirname, "..", "..")

/** Where the end-to-end specs live (`*.spec.ts`, never picked up by jest). */
const TestPath = path.join(PackagePath, "tests", "e2e")

/** Spec file pattern. */
const SpecPattern = "**/*.spec.ts"

/**
 * Per-test output (traces, screenshots). Absolute, because a relative path resolves against this
 * directory; under `lib/`, because `dist/` is the bundle the service serves.
 */
const OutputPath = path.join(PackagePath, "lib", "playwright", "test-results")

/** Reporter of a terminal run. */
const Reporter = "list"

/** The browser project every spec runs in. */
const BrowserProject = "chromium"

/** Device profile of {@link BrowserProject}. */
const BrowserDevice = "Desktop Chrome"

/** One daemon serves every spec, so the specs run one at a time. */
const Workers = 1

/** Keep a trace of a failed test for `playwright show-trace`. */
const TraceMode = "retain-on-failure"

export default defineConfig({
  testDir: TestPath,
  testMatch: SpecPattern,
  outputDir: OutputPath,
  reporter: Reporter,
  forbidOnly: true,
  fullyParallel: false,
  workers: Workers,
  retries: 0,
  // Builds the dashboard if needed, starts the Python daemon (fake model, temporary storage, a
  // free port), indexes and searches a fixture project; the teardown stops it and cleans up.
  globalSetup: path.join(import.meta.dirname, "globalSetup.ts"),
  globalTeardown: path.join(import.meta.dirname, "globalTeardown.ts"),
  use: { trace: TraceMode },
  projects: [{ name: BrowserProject, use: { ...devices[BrowserDevice] } }]
})
