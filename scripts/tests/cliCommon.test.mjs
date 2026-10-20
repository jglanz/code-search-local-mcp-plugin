/** cli-common helpers: strict argument parsing, the entry guard, the file walk, error descriptions, runMain. */
import assert from "node:assert/strict"
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { afterEach, describe, it } from "node:test"

import {
  ExitCode,
  RepoPath,
  UsageError,
  describeError,
  isEntryScript,
  listFiles,
  parseArguments,
  runMain,
  warn
} from "../common/cli-common.mjs"

/**
 * Run `body` with stderr captured.
 *
 * @param {() => Promise<void>} body the code whose stderr is captured.
 * @return {Promise<string>} everything written to stderr meanwhile.
 */
async function captureStderr(body) {
  const chunks = [],
    write = process.stderr.write
  process.stderr.write = chunk => chunks.push(String(chunk))
  try {
    await body()
  } finally {
    process.stderr.write = write
  }
  return chunks.join("")
}

describe("RepoPath", () => {
  it("is the workspace root holding pnpm-workspace.yaml", () => {
    assert.equal(existsSync(path.join(RepoPath, "pnpm-workspace.yaml")), true)
  })

  it("is absolute and never the scripts directory itself", () => {
    assert.equal(path.isAbsolute(RepoPath), true)
    assert.notEqual(RepoPath, path.resolve(import.meta.dirname, ".."))
  })
})

describe("parseArguments", () => {
  it("parses declared boolean and string flags", () => {
    assert.deepEqual(parseArguments({ booleans: ["check"], strings: ["repo-path"] }, ["--check", "--repo-path", "x"]), {
      check: true,
      "repo-path": "x"
    })
  })

  it("rejects unknown flags, positionals, repeated and empty string flags with a UsageError", () => {
    assert.throws(() => parseArguments({}, ["--nope"]), UsageError)
    assert.throws(() => parseArguments({}, ["stray"]), /unexpected argument/)
    assert.throws(() => parseArguments({ strings: ["p"] }, ["--p", "a", "--p", "b"]), /more than once/)
    assert.throws(() => parseArguments({ strings: ["p"] }, ["--p="]), /requires a value/)
  })

  it("rejects a negated string flag, which would carry false instead of a value", () => {
    assert.throws(
      () => parseArguments({ strings: ["output"] }, ["--no-output"]),
      error => error instanceof UsageError && error.message === "--output requires a value"
    )
  })

  it("rejects a value given to a boolean flag, and still accepts its negation", () => {
    assert.throws(
      () => parseArguments({ booleans: ["check"] }, ["--check=yes"]),
      error => error instanceof UsageError && error.message === "--check takes no value"
    )
    assert.throws(() => parseArguments({ booleans: ["check"] }, ["--check=false"]), /takes no value/)
    assert.deepEqual(parseArguments({ booleans: ["check"] }, ["--no-check"]), { check: false })
  })
})

describe("warn", () => {
  it("writes the message and a newline to stderr", async () => {
    assert.equal(await captureStderr(async () => warn("careful")), "careful\n")
  })

  it("writes an empty message as a bare newline, never nothing", async () => {
    assert.equal(await captureStderr(async () => warn("")), "\n")
  })
})

describe("isEntryScript", () => {
  it("is true for the invoked script", () => {
    assert.equal(isEntryScript(process.argv[1]), true)
  })

  it("is false for another module", () => {
    assert.equal(isEntryScript(path.join(import.meta.dirname, "..", "common", "cli-common.mjs")), false)
  })
})

describe("listFiles", () => {
  const roots = []
  afterEach(() => roots.splice(0).forEach(root => rmSync(root, { recursive: true, force: true })))

  it("lists files recursively, skipping the named directories", () => {
    const root = mkdtempSync(path.join(tmpdir(), "list-files-"))
    roots.push(root)
    mkdirSync(path.join(root, "a", "node_modules"), { recursive: true })
    writeFileSync(path.join(root, "a", "x.ts"), "")
    writeFileSync(path.join(root, "a", "node_modules", "y.js"), "")
    assert.deepEqual(listFiles(root, ["node_modules"]), [path.join(root, "a", "x.ts")])
  })

  it("returns nothing for a missing directory", () => {
    assert.deepEqual(listFiles(path.join(tmpdir(), "does-not-exist-code-search-local"), []), [])
  })
})

describe("describeError", () => {
  it("joins the message chain, outermost first", () => {
    const error = new TypeError("fetch failed", { cause: new Error("connect ECONNREFUSED 127.0.0.1:1") })
    assert.equal(describeError(error), "fetch failed: connect ECONNREFUSED 127.0.0.1:1")
  })

  it("describes a non-Error value and stops at a cyclic cause", () => {
    assert.equal(describeError("EPIPE"), "EPIPE")
    const cyclic = new Error("loop")
    cyclic.cause = cyclic
    assert.ok(describeError(cyclic).startsWith("loop: loop"))
  })
})

describe("runMain", () => {
  afterEach(() => {
    process.exitCode = 0
  })

  it("sets the exit code main returns", async () => {
    await runMain(async () => ExitCode.failure)
    assert.equal(process.exitCode, ExitCode.failure)
  })

  it("maps a UsageError to the usage exit code and other errors to failure", async () => {
    await runMain(() => {
      throw new UsageError("bad flag")
    })
    assert.equal(process.exitCode, ExitCode.usage)
    await runMain(() => {
      throw new Error("crash")
    })
    assert.equal(process.exitCode, ExitCode.failure)
  })

  it("prints the whole cause chain and context of a failure", async () => {
    const error = new Error("probe failed", { cause: new Error("socket hang up") })
    error.context = { id: "tokenize.prompt" }
    const printed = await captureStderr(() =>
      runMain(() => {
        throw error
      })
    )
    assert.equal(process.exitCode, ExitCode.failure)
    assert.match(printed, /probe failed/)
    assert.match(printed, /socket hang up/)
    assert.match(printed, /tokenize\.prompt/)
  })
})
