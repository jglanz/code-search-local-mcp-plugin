#!/usr/bin/env node
/**
 * The workspace gate, one stage at a time, each under its own deadline and in its own process
 * group (a deadline or an interrupt TERMs the whole group, then KILLs whatever of it is still
 * alive after a grace period):
 *
 *   layout → conventions → format → lint → build → tests
 *
 * The gate covers the TypeScript workspace (formatting covers its TypeScript, Markdown and YAML,
 * the API package's `openapi.yaml` included); the Python service package is checked by its own
 * hatch commands. A stage whose script does not exist yet is reported as skipped, never as
 * passed.
 *
 * Usage:
 *   ./scripts/check.mjs
 *
 * Options:
 *   none (any option or argument is a usage error, exit 2)
 *
 * Exit codes:
 *   0  every stage passed or was skipped (script not written yet)
 *   1  a stage failed, exceeded its deadline, could not start, or was interrupted
 *   2  usage error (any option or argument was given)
 *
 * Examples:
 *   ./scripts/check.mjs
 *   pnpm check
 */

import { $, chalk, echo, fs, os, path } from "zx"

import { ExitCode, RepoPath, isEntryScript, parseArguments, runMain } from "./common/cli-common.mjs"

/**
 * Deadline of a long stage (build, every test); a stage still running then is stopped and fails
 * the gate. Lowering it fails a slow but healthy build; raising it lets a hung stage hold the
 * gate longer.
 */
const LongStageTimeoutMs = 15 * 60_000

/**
 * Deadline of a quick stage (a static check, lint); a stage still running then is stopped and
 * fails the gate. Lowering it fails a slow but healthy check; raising it lets a hung check hold
 * the gate longer.
 */
const QuickStageTimeoutMs = 3 * 60_000

/**
 * Interval of the "still running" line; lowering it floods the log, raising it leaves a long
 * stage silent for longer.
 */
const HeartbeatMs = 30_000

/**
 * Grace between TERM and KILL for a stopped stage's process group. Lowering it KILLs
 * descendants before they can clean up; raising it delays a failed gate's exit by up to this
 * long when a descendant ignores TERM.
 */
const KillGraceMs = 5_000

/** Shell exit status for "command not found". */
const CommandNotFoundExitCode = 127

/** Offset the shell adds to a signal number when its child is killed by it. */
const ShellSignalExitOffset = 128

/** Signal name by number (for shell-reported 128+N exits). */
const SignalNames = Object.freeze(
  Object.fromEntries(Object.entries(os.constants.signals).map(([name, number]) => [number, name]))
)

/** Signals that interrupt the active stage. */
const InterruptSignals = Object.freeze(["SIGINT", "SIGTERM"])

/** A stage that failed and has already printed why; {@link check} rejects with it. */
export class StageFailure extends Error {
  /**
   * @param {string} message what failed (already printed).
   */
  constructor(message) {
    super(message)
    this.name = "StageFailure"
  }
}

/**
 * Print a stage failure and build the {@link StageFailure} to throw.
 *
 * @param {string} message what failed.
 * @return {StageFailure} the failure.
 */
function newStageFailure(message) {
  echo(chalk.red(message))
  return new StageFailure(message)
}

/**
 * A stage running one of this directory's scripts.
 *
 * @param {string} label the stage name.
 * @param {string} script the script file name.
 * @param {number} timeoutMs the deadline.
 * @return {{ label: string, command: string, args: string[], timeoutMs: number, requiredFile: string }} the stage.
 */
export function newScriptStage(label, script, timeoutMs = QuickStageTimeoutMs) {
  const command = path.join(RepoPath, "scripts", script)
  return { label, command, args: [], timeoutMs, requiredFile: command }
}

/** The gate, in order. */
export const Stages = Object.freeze([
  newScriptStage("layout", "check-package-layout.mjs"),
  newScriptStage("conventions", "check-conventions.mjs"),
  { label: "format", command: "pnpm", args: ["format:check"], timeoutMs: QuickStageTimeoutMs, requiredFile: null },
  { label: "lint", command: "pnpm", args: ["lint"], timeoutMs: QuickStageTimeoutMs, requiredFile: null },
  { label: "build", command: "pnpm", args: ["build"], timeoutMs: LongStageTimeoutMs, requiredFile: null },
  { label: "tests", command: "pnpm", args: ["test"], timeoutMs: LongStageTimeoutMs, requiredFile: null }
])

/**
 * Signal a process group, ignoring one that already exited.
 *
 * @param {number} pid the group leader's pid.
 * @param {string} signal the signal name.
 */
function signalGroup(pid, signal) {
  try {
    process.kill(-pid, signal)
  } catch (error) {
    if (error.code !== "ESRCH") echo(chalk.red(`[check] could not send ${signal} to group ${pid}: ${error.message}`))
  }
}

/**
 * Whether any process of a group is still alive (signal 0 probes without signalling).
 *
 * @param {number} pid the group leader's pid.
 * @return {boolean} false only when the group is gone (ESRCH); a group we may not signal
 *   (EPERM) counts as alive.
 */
export function isGroupAlive(pid) {
  try {
    process.kill(-pid, 0)
    return true
  } catch (error) {
    return error.code !== "ESRCH"
  }
}

/**
 * Describe a non-zero outcome.
 *
 * @param {{ exitCode: number|null, signal: string|null }} output the stage's process output.
 * @return {string} the exit code or signal.
 */
export function describeExit({ exitCode, signal }) {
  if (signal != null) return signal
  const shellSignal = exitCode > ShellSignalExitOffset ? SignalNames[exitCode - ShellSignalExitOffset] : null
  return shellSignal == null ? String(exitCode) : `exited ${exitCode} (${shellSignal})`
}

/**
 * Run one stage with progress, a deadline and TERM → KILL escalation over its process group.
 *
 * @param {string} command the executable.
 * @param {string[]} args its arguments.
 * @param {object} options
 * @param {string} options.label stage name.
 * @param {number} options.timeoutMs deadline.
 * @param {string} [options.cwd] working directory (default: the workspace root).
 * @return {Promise<void>} resolves when the stage passes; rejects with a {@link StageFailure},
 *   already printed, when it does not.
 */
export async function runStage(command, args, { label, timeoutMs, cwd = RepoPath }) {
  const started = performance.now(),
    elapsed = () => ((performance.now() - started) / 1000).toFixed(1),
    child = $({ cwd, stdio: "inherit", detached: true, nothrow: true })`${command} ${args}`
  let failure = null,
    escalation = null
  const stop = reason => {
      if (failure != null) return
      failure = newStageFailure(`[check] ${label}: ${reason} after ${elapsed()}s`)
      signalGroup(child.pid, "SIGTERM")
      escalation = setTimeout(() => signalGroup(child.pid, "SIGKILL"), KillGraceMs)
    },
    interrupted = () => stop("interrupted"),
    deadline = setTimeout(() => stop("deadline exceeded"), timeoutMs),
    heartbeat = setInterval(() => echo(`[check] ${label}: running (${elapsed()}s)`), HeartbeatMs)
  echo(`[check] ${label}: started`)
  InterruptSignals.forEach(signal => process.once(signal, interrupted))
  const output = await child.finally(() => {
    clearTimeout(deadline)
    clearInterval(heartbeat)
    InterruptSignals.forEach(signal => process.removeListener(signal, interrupted))
  })
  if (failure != null) {
    // The stage's own process has exited. When its whole group is gone the pending KILL is
    // cancelled at once, so it can never hit a reused process-group id; when a descendant
    // ignored TERM and still holds the group, the KILL is left to fire at the end of its grace
    // period before the failure is reported.
    if (isGroupAlive(child.pid)) await new Promise(resolve => setTimeout(resolve, KillGraceMs))
    clearTimeout(escalation)
    throw failure
  }
  if (output.exitCode === CommandNotFoundExitCode)
    throw newStageFailure(`[check] ${label}: could not start ${command} (command not found)`)
  if (output.exitCode !== ExitCode.success)
    throw newStageFailure(`[check] ${label}: failed (${describeExit(output)}) after ${elapsed()}s`)
  echo(`[check] ${label}: passed (${elapsed()}s)`)
}

/**
 * Run every stage in order, stopping at the first failure; a stage whose script is not written
 * yet is reported as skipped.
 *
 * @param {readonly object[]} [stages] the stages (default: {@link Stages}).
 * @return {Promise<void>} resolves when every stage passed or was skipped; rejects with the first
 *   {@link StageFailure}.
 */
export async function check(stages = Stages) {
  await stages.reduce(
    (previous, { label, command, args, timeoutMs, requiredFile }) =>
      previous.then(() => {
        if (requiredFile != null && !fs.existsSync(requiredFile)) {
          echo(chalk.yellow(`[check] ${label}: skipped (${path.relative(RepoPath, requiredFile)} not written yet)`))
          return null
        }
        return runStage(command, args, { label, timeoutMs })
      }),
    Promise.resolve()
  )
}

if (isEntryScript(import.meta.filename)) {
  await runMain(async () => {
    parseArguments()
    return check().then(
      () => ExitCode.success,
      error => {
        // A StageFailure was printed by runStage; anything else is a defect of this script,
        // rethrown so runMain prints it in full.
        if (error instanceof StageFailure) return ExitCode.failure
        throw error
      }
    )
  })
}
