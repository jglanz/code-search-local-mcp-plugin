import { spawn, spawnSync } from "node:child_process"
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  realpathSync,
  writeFileSync
} from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { setTimeout as sleep } from "node:timers/promises"

import getPort from "get-port"

import {
  ApiPaths,
  type IndexRequest,
  type Job,
  type SearchRequest,
  type StatsSnapshot
} from "@code-search-local/code-search-local-api"

import { E2eEnvironment } from "./E2eEnvironment.js"

/** This package's root. */
const PackagePath = path.resolve(import.meta.dirname, "..", "..")

/** The repository root. */
const RepoPath = path.resolve(PackagePath, "..", "..")

/** The Python service package (the daemon's `PYTHONPATH` and working directory). */
const ServicePackagePath = path.join(RepoPath, "packages", "code-search-local")

/** The CPU backend environment's interpreter (`hatch run cpu:sync`). */
const PythonPath = path.join(RepoPath, ".venvs", "cpu", "bin", "python")

/** The built dashboard the daemon serves under `/ui/`. */
const DistPath = path.join(PackagePath, "dist")

/** The page whose presence means the dashboard is built. */
const IndexHtmlPath = path.join(DistPath, "index.html")

/** The daemon's test harness module (`packages/code-search-local/tests/daemon.py`). */
const DaemonModule = "tests.daemon"

/** Python's run-a-module flag. */
const ModuleFlag = "-m"

/** The harness option naming the storage directory. */
const StorageOption = "--storage"

/** The harness option naming the port. */
const PortOption = "--port"

/** The harness flag selecting deterministic fake embeddings (no model download). */
const FakeModelFlag = "--fake"

/** The service's variable naming the dashboard directory it serves. */
const WebappDirVariable = "CODE_SEARCH_WEBAPP_DIR"

/** Subdirectory of the temporary root holding the daemon's storage. */
const StorageSubpath = "storage"

/** Subdirectory of the temporary root holding the fixture project. */
const ProjectSubpath = "sample-project"

/** Encoding of the daemon's text files. */
const TextEncoding = "utf8"

/** Open mode of the daemon log (append). */
const AppendMode = "a"

/** Method of a body-less API request. */
const GetMethod = "GET"

/** Method of an API request with a JSON body. */
const PostMethod = "POST"

/** Header carrying the bearer token. */
const AuthorizationHeader = "Authorization"

/** Header naming the body's media type. */
const ContentTypeHeader = "Content-Type"

/** Media type of every API body. */
const JsonMediaType = "application/json"

/** Interface the daemon binds; never a LAN address. */
const LoopbackHost = "127.0.0.1"

/** Prefix of the temporary directory. */
const RootPrefix = "code-search-local-e2e-"

/** The daemon's file of the service token (in its storage directory). */
const AuthFile = "auth.json"

/** The daemon's combined stdout/stderr, kept for diagnosing a failed start. */
const DaemonLogFile = "daemon.log"

/** Longest wait for the daemon to answer its health check. */
const StartupTimeoutMs = 90_000

/** Pause between two health checks. */
const StartupPollMs = 250

/** Status of a job that committed a generation. */
const SucceededStatus: Job["status"] = "succeeded"

/** The search the fixture project receives, so the dashboard has analytics to show. */
const FixtureQuery = "add two numbers and return the sum"

/**
 * The fixture project: a few Python files in nested directories, so the dashboard's tree has
 * directories to aggregate.
 */
const FixtureFiles: Readonly<Record<string, string>> = Object.freeze({
  "app/main.py": [
    "from app.util.numbers import add",
    "",
    "",
    "def main() -> None:",
    '    """Print the sum of two numbers."""',
    "    print(add(2, 3))",
    ""
  ].join("\n"),
  "app/util/numbers.py": [
    "def add(left: int, right: int) -> int:",
    '    """Add two numbers and return the sum."""',
    "    return left + right",
    "",
    "",
    "def subtract(left: int, right: int) -> int:",
    '    """Subtract right from left."""',
    "    return left - right",
    ""
  ].join("\n"),
  "app/util/strings.py": [
    "def shout(text: str) -> str:",
    '    """Return the text in upper case with an exclamation mark."""',
    '    return text.upper() + "!"',
    ""
  ].join("\n"),
  "scripts/report.py": [
    "import json",
    "",
    "",
    "def write_report(path: str, totals: dict) -> None:",
    '    """Write totals as indented JSON."""',
    '    with open(path, "w") as handle:',
    "        json.dump(totals, handle, indent=2)",
    ""
  ].join("\n")
})

/** The daemon's `auth.json`. */
interface AuthFileContent {
  /** The service token. */
  token: string
}

/**
 * Run a command, failing with its exit status.
 *
 * @param command the executable.
 * @param args its arguments.
 * @param cwd the working directory.
 */
function run(command: string, args: string[], cwd: string): void {
  const { status, error } = spawnSync(command, args, { cwd, stdio: "inherit" })
  if (error != null || status !== 0)
    throw new Error(`${command} ${args.join(" ")} failed (status ${status})`, {
      cause: error
    })
}

/**
 * Write the fixture project.
 *
 * @param projectPath its root.
 */
function writeFixtureProject(projectPath: string): void {
  Object.entries(FixtureFiles).forEach(([subpath, text]) => {
    const file = path.join(projectPath, subpath)
    mkdirSync(path.dirname(file), { recursive: true })
    writeFileSync(file, text)
  })
}

/**
 * Call the service's JSON API with the bearer token.
 *
 * @param serviceUrl the service origin.
 * @param token the bearer token.
 * @param route the API path.
 * @param body the JSON body (a POST), or undefined (a GET).
 * @returns the parsed response body.
 * @throws Error on a non-2xx answer, with the status and body.
 */
async function callApi<T>(
  serviceUrl: string,
  token: string,
  route: string,
  body?: unknown
): Promise<T> {
  const response = await fetch(`${serviceUrl}${route}`, {
      method: body == null ? GetMethod : PostMethod,
      headers: {
        [AuthorizationHeader]: `Bearer ${token}`,
        [ContentTypeHeader]: JsonMediaType
      },
      body: body == null ? undefined : JSON.stringify(body)
    }),
    text = await response.text()
  if (!response.ok)
    throw new Error(`${route} answered ${response.status}: ${text}`)
  return JSON.parse(text) as T
}

/**
 * Wait until the daemon wrote its token and answers its health check.
 *
 * @param serviceUrl the service origin.
 * @param storagePath its storage directory.
 * @param logPath its log, quoted when it never comes up.
 * @returns the bearer token.
 */
async function waitForDaemon(
  serviceUrl: string,
  storagePath: string,
  logPath: string
): Promise<string> {
  const deadline = Date.now() + StartupTimeoutMs,
    authPath = path.join(storagePath, AuthFile),
    poll = async (): Promise<string> => {
      if (Date.now() > deadline)
        throw new Error(
          `the daemon did not come up within ${StartupTimeoutMs} ms; its log:\n${readFileSync(logPath, TextEncoding)}`
        )
      if (existsSync(authPath)) {
        const { token } = JSON.parse(
          readFileSync(authPath, TextEncoding)
        ) as AuthFileContent
        const healthy = await callApi(serviceUrl, token, ApiPaths.Health).then(
          () => true,
          () => false
        )
        if (healthy) return token
      }
      await sleep(StartupPollMs)
      return poll()
    }
  return poll()
}

/**
 * Build the dashboard when needed, start the Python daemon (fake model, temporary storage, a free
 * port) serving it, index a fixture project, run one search, and hand everything the specs and
 * the teardown need to them through {@link E2eEnvironment}.
 */
export default async function globalSetup(): Promise<void> {
  if (!existsSync(IndexHtmlPath)) run("pnpm", ["run", "build"], PackagePath)
  const root = realpathSync(mkdtempSync(path.join(tmpdir(), RootPrefix))),
    storagePath = path.join(root, StorageSubpath),
    projectPath = path.join(root, ProjectSubpath),
    logPath = path.join(root, DaemonLogFile),
    port = await getPort({ host: LoopbackHost }),
    serviceUrl = `http://${LoopbackHost}:${port}`
  process.env[E2eEnvironment.RootVariable] = root
  mkdirSync(storagePath, { recursive: true })
  writeFixtureProject(projectPath)
  const log = openSync(logPath, AppendMode),
    daemon = spawn(
      PythonPath,
      [
        ModuleFlag,
        DaemonModule,
        StorageOption,
        storagePath,
        PortOption,
        String(port),
        FakeModelFlag
      ],
      {
        cwd: ServicePackagePath,
        detached: true,
        stdio: ["ignore", log, log],
        env: {
          ...process.env,
          PYTHONPATH: ServicePackagePath,
          [WebappDirVariable]: DistPath
        }
      }
    )
  daemon.unref()
  process.env[E2eEnvironment.DaemonPidVariable] = String(daemon.pid)
  const token = await waitForDaemon(serviceUrl, storagePath, logPath),
    indexRequest: IndexRequest = { directory_path: projectPath, wait: true },
    job = await callApi<Job>(serviceUrl, token, ApiPaths.Index, indexRequest)
  if (job.status !== SucceededStatus)
    throw new Error(
      `indexing the fixture project ended ${job.status}: ${job.error}`
    )
  const searchRequest: SearchRequest = {
    project_path: job.project_path,
    query: FixtureQuery
  }
  await callApi(serviceUrl, token, ApiPaths.Search, searchRequest)
  const snapshot = await callApi<StatsSnapshot>(
      serviceUrl,
      token,
      ApiPaths.Stats
    ),
    { [job.project_path]: project } = snapshot.projects
  process.env[E2eEnvironment.ServiceUrlVariable] = serviceUrl
  process.env[E2eEnvironment.TokenVariable] = token
  process.env[E2eEnvironment.ProjectPathVariable] = project.project_path
  process.env[E2eEnvironment.ProjectIdVariable] = project.project_id
}
