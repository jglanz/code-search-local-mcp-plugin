/**
 * check-package-layout over fixture workspaces: a clean tree passes, stray root and package
 * entries are reported.
 */
import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { describe, it } from "node:test"

import {
  IgnoredEntries,
  RootGeneratedEntries,
  SourceOutputAllowlist,
  findOutDirViolations,
  findViolations,
  readOutDir
} from "../check-package-layout.mjs"

const FixturesPath = path.join(import.meta.dirname, "fixtures", "layout")

/**
 * Run a check on a fresh copy of the clean fixture workspace, removed afterwards.
 *
 * @param {(root: string) => void} check receives the copy's root.
 */
function withCleanCopy(check) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "layout-"))
  try {
    fs.cpSync(path.join(FixturesPath, "clean"), root, { recursive: true })
    check(root)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
}

describe("check-package-layout", () => {
  it("accepts a conforming workspace", () => {
    assert.deepEqual(findViolations(path.join(FixturesPath, "clean")), [])
  })

  it("ignores tool caches, git, editor and agent state, at the root and in a package", () =>
    withCleanCopy(root => {
      ;[
        ".git",
        ".omc/state",
        ".idea",
        ".cache",
        "packages/.omc/state",
        "packages/a/.omc/state",
        "packages/a/.cache"
      ].forEach(directory => fs.mkdirSync(path.join(root, directory), { recursive: true }))
      fs.writeFileSync(path.join(root, ".gitignore"), ".omc/\n")
      assert.deepEqual(findViolations(root), [])
    })
  )

  it("ignores Python environments and caches at the root, in a package and under src/", () =>
    withCleanCopy(root => {
      ;[".venv", ".venvs/cpu", ".pytest_cache", ".ruff_cache", ".remember", ".test-artifacts", "__pycache__"].forEach(
        directory => fs.mkdirSync(path.join(root, directory), { recursive: true })
      )
      ;["packages/a/__pycache__", "packages/a/.pytest_cache", "packages/a/src/pkg/__pycache__"].forEach(directory =>
        fs.mkdirSync(path.join(root, directory), { recursive: true })
      )
      fs.writeFileSync(path.join(root, "packages/a/src/pkg/module.py"), "VALUE = 1\n")
      fs.writeFileSync(path.join(root, "packages/a/src/pkg/__pycache__/module.cpython-312.pyc"), "")
      assert.ok(IgnoredEntries.includes("__pycache__"))
      assert.deepEqual(findViolations(root), [])
    })
  )

  it("skips the root's generated Python output, but reports the same names in a package", () =>
    withCleanCopy(root => {
      RootGeneratedEntries.forEach(name =>
        name.includes(".") ? fs.writeFileSync(path.join(root, name), "") : fs.mkdirSync(path.join(root, name))
      )
      assert.deepEqual(findViolations(root), [])
      fs.mkdirSync(path.join(root, "packages/a/logs"))
      fs.writeFileSync(path.join(root, "packages/a/coverage.json"), "{}\n")
      assert.deepEqual(findViolations(root), ["packages/a/coverage.json", "packages/a/logs/"])
    })
  )

  it("accepts a package root holding only an OpenAPI document and a README (no package.json yet)", () =>
    withCleanCopy(root => {
      fs.mkdirSync(path.join(root, "packages/api"))
      fs.writeFileSync(path.join(root, "packages/api/openapi.yaml"), "openapi: 3.1.0\n")
      fs.writeFileSync(path.join(root, "packages/api/README.md"), "")
      assert.deepEqual(findViolations(root), [])
      fs.writeFileSync(path.join(root, "packages/api/openapi.json"), "{}\n")
      assert.deepEqual(findViolations(root), ["packages/api/openapi.json"])
    })
  )

  it("accepts the Python project's root entries beside the workspace's", () =>
    withCleanCopy(root => {
      ;["pyproject.toml", "uv.lock", "LICENSE", "AGENTS.md", "CLAUDE.md", "README.md", "STYLE.md"].forEach(file =>
        fs.writeFileSync(path.join(root, file), "")
      )
      ;["plugins", ".claude-plugin", ".agents", ".claude", ".github", "docs", "etc", "scripts"].forEach(directory =>
        fs.mkdirSync(path.join(root, directory))
      )
      assert.deepEqual(findViolations(root), [])
      fs.mkdirSync(path.join(root, "src"))
      assert.deepEqual(findViolations(root), ["src/"])
    })
  )

  it("reports stray workspace-root and package-root entries, and compiler output in src/", () => {
    assert.deepEqual(findViolations(path.join(FixturesPath, "bad")), [
      "notes.txt",
      "packages/a/misc/",
      "packages/a/src/nested/Stale.d.ts",
      "packages/a/src/nested/Stale.d.ts.map",
      "packages/a/src/nested/Stale.js",
      "packages/a/src/nested/Stale.js.map",
      "packages/a/stray.config.js"
    ])
  })

  it("reports a tsconfig outDir outside lib/{esm,cjs,test,node} and accepts the four", () =>
    withCleanCopy(root => {
      const write = (name, outDir) =>
        fs.writeFileSync(path.join(root, "packages/a", name), `${JSON.stringify({ compilerOptions: { outDir } })}\n`)
      ;["esm", "cjs", "test", "node"].forEach(flavour => write(`tsconfig.${flavour}.json`, `lib/${flavour}`))
      write("tsconfig.dot.json", "./lib/esm")
      assert.deepEqual(findOutDirViolations(root), [])
      write("tsconfig.app.json", "lib/app")
      write("tsconfig.jest.json", "lib/test-esm")
      write("tsconfig.src.json", "src")
      assert.deepEqual(findViolations(root), [
        "packages/a/tsconfig.app.json: outDir lib/app",
        "packages/a/tsconfig.jest.json: outDir lib/test-esm",
        "packages/a/tsconfig.src.json: outDir src"
      ])
    })
  )

  it("reads a tsconfig with comments and trailing commas, as tsc does", () =>
    withCleanCopy(root => {
      const write = (name, text) => fs.writeFileSync(path.join(root, "packages/a", name), text)
      write("tsconfig.esm.json", '{\n  // the build\n  "compilerOptions": {\n    /* emitted here */ "outDir": "lib/esm",\n  },\n}\n')
      write("tsconfig.app.json", '{\n  // emits beside the package\n  "compilerOptions": { "outDir": "dist/app" }\n}\n')
      assert.equal(readOutDir(path.join(root, "packages/a/tsconfig.esm.json")), "lib/esm")
      assert.deepEqual(findOutDirViolations(root), ["packages/a/tsconfig.app.json: outDir dist/app"])
    })
  )

  it("fails on a tsconfig tsc cannot parse, naming the file", () =>
    withCleanCopy(root => {
      fs.writeFileSync(path.join(root, "packages/a/tsconfig.bad.json"), '{ "compilerOptions": ')
      assert.throws(() => findOutDirViolations(root), /tsconfig\.bad\.json/)
    })
  )

  it("accepts the hand-written declaration files of the allow-list in src/", () =>
    withCleanCopy(root => {
      SourceOutputAllowlist.forEach(file => {
        fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true })
        fs.writeFileSync(path.join(root, file), "export {}\n")
    })
    fs.writeFileSync(path.join(root, "packages/code-search-local-webapp/package.json"), "{}\n")
    assert.deepEqual(findViolations(root), [])
    })
  )

  it("exits 1 from the command line when an entry is outside the standard", () => {
    const { status } = spawnSync(
      process.execPath,
      [path.join(import.meta.dirname, "..", "check-package-layout.mjs"), "--repo-path", path.join(FixturesPath, "bad")],
      { encoding: "utf8" }
    )
    assert.equal(status, 1)
  })

  it("exits 0 from the command line for a conforming workspace", () => {
    const { status } = spawnSync(
      process.execPath,
      [path.join(import.meta.dirname, "..", "check-package-layout.mjs"), "--repo-path", path.join(FixturesPath, "clean")],
      { encoding: "utf8" }
    )
    assert.equal(status, 0)
  })
})
