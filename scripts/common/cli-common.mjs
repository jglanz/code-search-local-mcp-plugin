/**
 * Helpers shared by the workspace's executable scripts (`scripts/*.mjs`): the workspace root,
 * the common exit codes, stderr messages, strict argument parsing, and the entry-script guard.
 *
 * Not executable itself; scripts import it as `./common/cli-common.mjs`.
 */

import { inspect } from "node:util"

import { chalk, fs, minimist, path } from "zx"

/** The workspace root (one level above `scripts/`). */
export const RepoPath = path.resolve(import.meta.dirname, "..", "..")

/**
 * Process exit codes shared by every script (each header documents its meaning there).
 *
 * - `success` (0): the script did its job / the check passed.
 * - `failure` (1): the check found a problem.
 * - `usage` (2): bad arguments or a missing input.
 */
export const ExitCode = Object.freeze({ success: 0, failure: 1, usage: 2 })

/** A bad command line or missing input; {@link runMain} maps it to {@link ExitCode}.usage. */
export class UsageError extends Error {
  /**
   * @param {string} message what was wrong.
   */
  constructor(message) {
    super(message)
    this.name = "UsageError"
  }
}

/** The minimist key holding positional arguments. */
const PositionalKey = "_"

/** Deepest cause chain {@link describeError} follows; guards against cyclic causes. */
const MaxDescribedCauses = 8

/** A `--name=value` argument; group 1 is the flag name. */
const AssignedFlagPattern = /^--([^=]+)=/

/**
 * Print a line on stderr.
 *
 * @param {string} message the text.
 */
export function warn(message) {
  process.stderr.write(`${message}\n`)
}

/**
 * Throw a {@link UsageError}.
 *
 * @param {string} message what was wrong.
 */
function throwUsage(message) {
  throw new UsageError(message)
}

/**
 * Parse the command line against declared flag kinds. Usage errors: an unknown flag, a
 * positional, a string flag without exactly one non-empty string value (`--name=`, a repeated
 * flag, or the negated `--no-name`), and a boolean flag given a value (`--name=value`; minimist
 * would silently read any value but `false` as true).
 *
 * @param {object} [kinds]
 * @param {readonly string[]} [kinds.booleans] boolean flags (without `--`).
 * @param {readonly string[]} [kinds.strings] string-valued flags (without `--`).
 * @param {readonly string[]} [args] the arguments (default: `process.argv.slice(2)`).
 * @return {Record<string, boolean|string|undefined>} flag name → value.
 */
export function parseArguments({ booleans = [], strings = [] } = {}, args = process.argv.slice(2)) {
  const { [PositionalKey]: positionals, ...flags } = minimist([...args], {
      boolean: [...booleans],
      string: [...strings]
    }),
    unknown = Object.keys(flags).filter(flag => !booleans.includes(flag) && !strings.includes(flag))
  if (unknown.length > 0) throwUsage(`unknown option(s): ${unknown.map(flag => `--${flag}`).join(", ")}`)
  if (positionals.length > 0) throwUsage(`unexpected argument(s): ${positionals.join(" ")}`)
  strings
    .filter(flag => flag in flags)
    .forEach(flag => {
      if (Array.isArray(flags[flag])) throwUsage(`--${flag} given more than once`)
      if (typeof flags[flag] !== "string" || flags[flag].length === 0) throwUsage(`--${flag} requires a value`)
    })
  args
    .map(argument => argument.match(AssignedFlagPattern)?.[1])
    .filter(flag => booleans.includes(flag))
    .forEach(flag => throwUsage(`--${flag} takes no value`))
  return flags
}

/**
 * Whether the importer is the process entry script (so `main` runs only when executed, not when
 * a test imports it).
 *
 * @param {string} filename the importer's `import.meta.filename`.
 * @return {boolean} true when executed directly.
 */
export function isEntryScript(filename) {
  const invoked = process.argv[1]
  return invoked != null && fs.existsSync(invoked) && fs.realpathSync(invoked) === fs.realpathSync(filename)
}

/**
 * Every file under `rootPath` (recursively), skipping the named directories at any depth.
 *
 * @param {string} rootPath the directory to walk.
 * @param {readonly string[]} skippedDirectories directory names never entered.
 * @return {string[]} absolute file paths, sorted.
 */
export function listFiles(rootPath, skippedDirectories) {
  if (!fs.existsSync(rootPath)) return []
  return fs
    .readdirSync(rootPath, { withFileTypes: true })
    .flatMap(entry =>
      entry.isDirectory()
        ? skippedDirectories.includes(entry.name)
          ? []
          : listFiles(path.join(rootPath, entry.name), skippedDirectories)
        : [path.join(rootPath, entry.name)]
    )
    .sort()
}

/**
 * One line describing an error and its cause chain (`fetch failed: connect ECONNREFUSED …`):
 * a transport error's own message is generic, its cause names what actually failed.
 *
 * @param {unknown} error the thrown value.
 * @param {number} [depth] causes already described (callers omit it).
 * @return {string} every message in the chain, outermost first, joined by `: `.
 */
export function describeError(error, depth = 0) {
  const { message = String(error), cause } = error instanceof Error ? error : {}
  return cause == null || depth >= MaxDescribedCauses ? message : `${message}: ${describeError(cause, depth + 1)}`
}

/**
 * Run a script's `main` and set the process exit code: its return value, {@link ExitCode}.usage
 * for a {@link UsageError}, {@link ExitCode}.failure for anything else thrown (printed with
 * `util.inspect`, so its stack, `cause` chain and `context` all survive).
 *
 * @param {() => Promise<number>|number} main the script body.
 * @return {Promise<void>} resolves once the exit code is set.
 */
export async function runMain(main) {
  try {
    process.exitCode = await main()
  } catch (error) {
    if (error instanceof UsageError) {
      warn(chalk.red(`Error: ${error.message}`))
      process.exitCode = ExitCode.usage
      return
    }
    warn(chalk.red(inspect(error, { depth: null })))
    process.exitCode = ExitCode.failure
  }
}
