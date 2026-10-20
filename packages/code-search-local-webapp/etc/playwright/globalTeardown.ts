import { rmSync } from "node:fs"
import { setTimeout as sleep } from "node:timers/promises"

import { E2eEnvironment } from "./E2eEnvironment.js"

/** Signal asking the daemon to shut down cleanly. */
const StopSignal = "SIGTERM"

/** Signal ending a daemon that ignored {@link StopSignal}. */
const KillSignal = "SIGKILL"

/** Signal 0 only probes whether a process group exists. */
const ProbeSignal = 0

/** `process.kill` error code for a process group that no longer exists. */
const NoSuchProcessCode = "ESRCH"

/** Longest wait for the daemon to exit after {@link StopSignal}. */
const StopTimeoutMs = 10_000

/** Pause between two exit probes. */
const StopPollMs = 100

/**
 * Signal the daemon's process group.
 *
 * @param pid the group leader's pid.
 * @param signal the signal.
 * @returns false once the group is gone, true while it exists.
 */
function signalGroup(pid: number, signal: NodeJS.Signals | number): boolean {
  try {
    process.kill(-pid, signal)
    return true
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === NoSuchProcessCode)
      return false
    throw new Error(`could not signal the e2e daemon group ${pid}`, {
      cause: error
    })
  }
}

/**
 * Wait until the daemon's group is gone.
 *
 * @param pid the group leader's pid.
 * @param deadline when to stop waiting (ms since the epoch).
 * @returns true when it exited in time.
 */
async function waitForExit(pid: number, deadline: number): Promise<boolean> {
  if (!signalGroup(pid, ProbeSignal)) return true
  if (Date.now() > deadline) return false
  await sleep(StopPollMs)
  return waitForExit(pid, deadline)
}

/**
 * Stop the daemon `globalSetup.ts` started (TERM, then KILL after a grace period) and remove the
 * temporary storage, fixture project and log.
 */
export default async function globalTeardown(): Promise<void> {
  const {
    [E2eEnvironment.DaemonPidVariable]: pidText,
    [E2eEnvironment.RootVariable]: root
  } = process.env
  if (pidText != null) {
    const pid = Number(pidText)
    if (signalGroup(pid, StopSignal)) {
      const exited = await waitForExit(pid, Date.now() + StopTimeoutMs)
      if (!exited) signalGroup(pid, KillSignal)
    }
  }
  if (root != null) rmSync(root, { recursive: true, force: true })
}
