/**
 * How `globalSetup.ts` hands the service under test to the specs and to `globalTeardown.ts`:
 * through the environment, because Playwright runs the setup in the runner process and the specs
 * in worker processes started after it (workers inherit the runner's environment).
 */
export namespace E2eEnvironment {
  /** The service's origin, e.g. `http://127.0.0.1:43123`. */
  export const ServiceUrlVariable = "CODE_SEARCH_E2E_SERVICE_URL"

  /** The service's bearer token (from `<storage>/auth.json`). */
  export const TokenVariable = "CODE_SEARCH_E2E_TOKEN"

  /** The indexed fixture project's canonical root. */
  export const ProjectPathVariable = "CODE_SEARCH_E2E_PROJECT_PATH"

  /** The fixture project's id (`project_id` in the snapshot). */
  export const ProjectIdVariable = "CODE_SEARCH_E2E_PROJECT_ID"

  /** The temporary directory holding the storage, the fixture project and the daemon log. */
  export const RootVariable = "CODE_SEARCH_E2E_ROOT"

  /** Process id (and process-group id) of the daemon under test. */
  export const DaemonPidVariable = "CODE_SEARCH_E2E_DAEMON_PID"
}

/** What the specs read from the environment. */
export interface E2eService {
  /** The service's origin. */
  serviceUrl: string

  /** Its bearer token. */
  token: string

  /** The indexed fixture project's root. */
  projectPath: string

  /** The fixture project's id. */
  projectId: string
}

/**
 * Read the service under test from the environment `globalSetup.ts` filled.
 *
 * @returns the service.
 * @throws Error when a variable is missing (the specs ran without the global setup).
 */
export function readE2eService(): E2eService {
  const read = (variable: string): string => {
    const { [variable]: value } = process.env
    if (value == null || value.length === 0)
      throw new Error(
        `${variable} is not set; run the specs through the Playwright config`
      )
    return value
  }
  return {
    serviceUrl: read(E2eEnvironment.ServiceUrlVariable),
    token: read(E2eEnvironment.TokenVariable),
    projectPath: read(E2eEnvironment.ProjectPathVariable),
    projectId: read(E2eEnvironment.ProjectIdVariable)
  }
}
