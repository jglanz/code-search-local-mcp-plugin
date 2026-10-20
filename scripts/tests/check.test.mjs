/** check.mjs: the stage order and runStage outcomes (pass, fail, command not found, deadline). */
import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import { once } from "node:events"
import { existsSync, mkdtempSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { afterEach, describe, it } from "node:test"

import { StageFailure, Stages, check, describeExit, isGroupAlive, newScriptStage, runStage } from "../check.mjs"

/** The stage order STYLE.md documents. */
const DocumentedOrder = ["layout", "conventions", "format", "lint", "build", "tests"]

describe("Stages", () => {
  it("runs in the documented order", () => {
    assert.deepEqual(
      Stages.map(({ label }) => label),
      DocumentedOrder
    )
  })

  it("gives every stage a deadline", () => {
    assert.ok(Stages.every(({ timeoutMs }) => timeoutMs > 0))
  })

  it("checks formatting with prettier --check, never --write", () => {
    const format = Stages.find(({ label }) => label === "format")
    assert.deepEqual([format.command, ...format.args], ["pnpm", "format:check"])
    assert.ok(!format.args.includes("format"), "the gate must not rewrite files")
  })
})

describe("runStage", () => {
  it("passes a command that exits 0", async () => {
    await runStage(process.execPath, ["-e", "process.exit(0)"], { label: "ok", timeoutMs: 10_000 })
  })

  it("fails on a non-zero exit, a missing command and a deadline, each as a StageFailure", async () => {
    await assert.rejects(
      runStage(process.execPath, ["-e", "process.exit(3)"], { label: "fails", timeoutMs: 10_000 }),
      error => error instanceof StageFailure && /fails: failed \(3\)/.test(error.message)
    )
    await assert.rejects(
      runStage("definitely-not-a-command-code-search-local", [], { label: "missing", timeoutMs: 10_000 }),
      error => error instanceof StageFailure && /could not start .* \(command not found\)/.test(error.message)
    )
    await assert.rejects(
      runStage(process.execPath, ["-e", "setTimeout(() => {}, 60_000)"], { label: "slow", timeoutMs: 300 }),
      error => error instanceof StageFailure && /slow: deadline exceeded/.test(error.message)
    )
  })
})

describe("check", () => {
  const roots = []
  afterEach(() => roots.splice(0).forEach(root => rmSync(root, { recursive: true, force: true })))

  it("skips a stage whose script is not written yet and runs the rest", async () => {
    await check([
      newScriptStage("not-yet", "no-such-script-code-search-local.mjs"),
      { label: "ok", command: process.execPath, args: ["-e", "process.exit(0)"], timeoutMs: 10_000, requiredFile: null }
    ])
  })

  it("stops at the first failing stage, never starting the next", async () => {
    const root = mkdtempSync(path.join(tmpdir(), "check-stages-")),
      marker = path.join(root, "second-ran")
    roots.push(root)
    await assert.rejects(
      check([
        { label: "first", command: process.execPath, args: ["-e", "process.exit(1)"], timeoutMs: 10_000, requiredFile: null },
        {
          label: "second",
          command: process.execPath,
          args: ["-e", `require("node:fs").writeFileSync(${JSON.stringify(marker)}, "")`],
          timeoutMs: 10_000,
          requiredFile: null
        }
      ]),
      error => error instanceof StageFailure && /first: failed/.test(error.message)
    )
    assert.equal(existsSync(marker), false, "the second stage must not run")
  })
})

describe("isGroupAlive", () => {
  it("is true for a running process group", async () => {
    const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 60_000)"], { detached: true, stdio: "ignore" })
    try {
      assert.equal(isGroupAlive(child.pid), true)
    } finally {
      process.kill(-child.pid, "SIGKILL")
      await once(child, "exit")
    }
  })

  it("is false once the group is gone", async () => {
    const child = spawn(process.execPath, ["-e", "process.exit(0)"], { detached: true, stdio: "ignore" })
    await once(child, "exit")
    assert.equal(isGroupAlive(child.pid), false)
  })
})

describe("describeExit", () => {
  it("names a signal, direct or shell-reported as 128+N", () => {
    assert.equal(describeExit({ exitCode: null, signal: "SIGKILL" }), "SIGKILL")
    assert.equal(describeExit({ exitCode: 143, signal: null }), "exited 143 (SIGTERM)")
  })

  it("prints a plain exit code", () => {
    assert.equal(describeExit({ exitCode: 3, signal: null }), "3")
  })
})

describe("newScriptStage", () => {
  it("points at the script under scripts/ and requires it to exist", () => {
    const stage = newScriptStage("layout", "check-package-layout.mjs")
    assert.ok(stage.command.endsWith("scripts/check-package-layout.mjs"))
    assert.equal(stage.requiredFile, stage.command)
  })

  it("uses the quick deadline by default", () => {
    assert.ok(newScriptStage("x", "x.mjs").timeoutMs < Stages.find(({ label }) => label === "tests").timeoutMs)
  })
})
