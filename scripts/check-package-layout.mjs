#!/usr/bin/env node
/**
 * Verify the workspace ROOT and every package ROOT hold only the standard layout entries.
 * Entries are found by a filesystem walk (untracked files count too). Entries that are never
 * authored content never count: tool caches, the git directory, editor/agent state and Python
 * environments anywhere ({@link IgnoredEntries}), plus the Python build, coverage and log output
 * written at the root ({@link RootGeneratedEntries}).
 *
 * Allowed at `packages/<name>/` (any directory under `packages/`, with or without a
 * package.json yet):
 *   files        package.json, README.md, CHANGELOG.md, LICENSE, .gitignore, .npmignore,
 *                tsconfig*.json, jest.config.{ts,js,cjs,mjs}, {webpack,esbuild}.config.{ts,mts,js,mjs,cjs},
 *                openapi.yaml
 *   directories  src/, tests/, bin/, scripts/, etc/, resources/, lib/, dist/  (+ node_modules/)
 *
 * Never in `packages/<name>/src/`: compiler output (`*.js`, `*.mjs`, `*.cjs`, `*.d.ts`, `*.map`). A
 * stray `tsc` emit next to its source shadows it: jest and webpack resolve `./X.js` to the stale
 * `.js` before the `.ts`. Hand-written declaration files are listed in {@link SourceOutputAllowlist}.
 *
 * Every `outDir` of a package's `tsconfig*.json` is one of `lib/esm`, `lib/cjs`, `lib/test` or
 * `lib/node` ({@link OutDirPattern}): sources are `src/*.ts` (tests `tests/`), and compiler output
 * (`*.js`, `*.d.ts`, `*.map`) lands only under those four.
 *
 * Allowed at the workspace root (the pnpm workspace and the Python project share it):
 *   files        package.json, pnpm-workspace.yaml, pnpm-lock.yaml, tsconfig.json, jest.config.ts,
 *                eslint.config.mjs, .prettierrc.js, .prettierignore, STYLE.md, README.md,
 *                CLAUDE.md, AGENTS.md, LICENSE, pyproject.toml, uv.lock, .gitignore
 *   directories  packages/, etc/, scripts/, docs/, plugins/, .claude-plugin/, .agents/,
 *                .claude/, .github/, node_modules/
 *
 * Usage:
 *   ./scripts/check-package-layout.mjs [--repo-path <dir>]
 *
 * Options:
 *   --repo-path <dir>   workspace to check (default: this workspace)
 *
 * Exit codes:
 *   0  every root is clean
 *   1  at least one entry is outside the standard (each one is printed)
 *   2  usage error / no packages/ directory
 *
 * Examples:
 *   ./scripts/check-package-layout.mjs
 *   ./scripts/check-package-layout.mjs --repo-path scripts/tests/fixtures/layout/bad
 */

import ts from "typescript"
import { chalk, echo, fs, path } from "zx"

import {
  ExitCode as CommonExitCode,
  RepoPath,
  UsageError,
  isEntryScript,
  listFiles,
  parseArguments,
  runMain
} from "./common/cli-common.mjs"

/** Process exit codes (documented in the header). */
const ExitCode = Object.freeze({
  ...CommonExitCode,
  violation: CommonExitCode.failure
})

/** Flag kinds this script accepts. */
const Flags = Object.freeze({ strings: ["repo-path"] })

/** The workspace directory holding every package. */
const PackagesSubpath = "packages"

/** A package's tsconfig file name. */
export const TsconfigPattern = /^tsconfig(\.[\w-]+)*\.json$/

/** Root files allowed in every package. */
export const PackageFilePatterns = Object.freeze([
  /^package\.json$/,
  /^README\.md$/,
  /^CHANGELOG\.md$/,
  /^LICENSE$/,
  /^\.gitignore$/,
  /^\.npmignore$/,
  TsconfigPattern,
  /^jest\.config\.(ts|js|cjs|mjs)$/,
  /^(webpack|esbuild)\.config\.(ts|mts|js|mjs|cjs)$/,
  // The HTTP API package's OpenAPI document, the source its schemas and types are generated from.
  /^openapi\.yaml$/
])

/** Root directories allowed in every package (node_modules is pnpm's, never authored). */
export const PackageDirectories = Object.freeze([
  "src",
  "tests",
  "bin",
  "scripts",
  "etc",
  "resources",
  "lib",
  "dist",
  "node_modules"
])

/** Files allowed at the workspace root. */
export const RootFiles = Object.freeze([
  "package.json",
  "pnpm-workspace.yaml",
  "pnpm-lock.yaml",
  "tsconfig.json",
  "jest.config.ts",
  "eslint.config.mjs",
  ".prettierrc.js",
  ".prettierignore",
  "STYLE.md",
  "README.md",
  "CLAUDE.md",
  "AGENTS.md",
  "LICENSE",
  "pyproject.toml",
  "uv.lock",
  ".gitignore"
])

/**
 * Never authored content, so never counted, at the root, in a package or under a package's
 * `src/` (all git-ignored): generated tool caches (`.cache`, the Python bytecode, pytest and
 * ruff caches), the git directory, editor/agent state, Python environments and the test
 * artifacts directory. Adding a name hides a stray entry of that name everywhere.
 */
export const IgnoredEntries = Object.freeze([
  ".cache",
  ".git",
  ".idea",
  ".omc",
  ".remember",
  ".venv",
  ".venvs",
  "__pycache__",
  ".pytest_cache",
  ".ruff_cache",
  ".test-artifacts"
])

/**
 * Generated output the Python tooling writes at the workspace root (all git-ignored): `hatch
 * build` distributions, coverage data and reports, and service logs. Only the root skips them;
 * in a package, `dist/` is an allowed directory and the others are violations.
 */
export const RootGeneratedEntries = Object.freeze([
  "dist",
  "logs",
  ".coverage",
  "coverage.json",
  "coverage.xml"
])

/** Files under a package's `src/` that look like compiler output: emitted code, declarations and maps. */
export const SourceOutputPattern = /\.(?:[mc]?js|map)$|\.d\.[mc]?ts$/

/**
 * Hand-written declaration files under `src/` (workspace-relative): webpack's module globals for
 * the webapp's asset imports. Anything else matching {@link SourceOutputPattern} is a stray
 * compiler emit.
 */
export const SourceOutputAllowlist = Object.freeze([
  "packages/code-search-local-webapp/src/webpackGlobals.d.ts"
])

/**
 * The output directories a package's tsconfig may emit to, relative to the package: ES modules,
 * CommonJS, test suites and Node-only code. Anything else (`lib/app`, a missing `lib/` prefix)
 * scatters compiler output where the build, the exports and the cleanup do not look.
 */
export const OutDirPattern = /^(?:\.\/)?lib\/(?:esm|cjs|test|node)\/?$/

/** Directories allowed at the workspace root. */
export const RootDirectories = Object.freeze([
  PackagesSubpath,
  "etc",
  "scripts",
  "docs",
  "plugins",
  ".claude-plugin",
  ".agents",
  ".claude",
  ".github",
  "node_modules"
])

/**
 * Root entries of a directory.
 *
 * @param {string} directoryPath the directory.
 * @param {readonly string[]} [skippedEntries] names never listed (default: {@link IgnoredEntries}).
 * @return {{ name: string, isDirectory: boolean }[]} its entries.
 */
function listEntries(directoryPath, skippedEntries = IgnoredEntries) {
  return fs
    .readdirSync(directoryPath, { withFileTypes: true })
    .filter(entry => !skippedEntries.includes(entry.name))
    .map(entry => ({ name: entry.name, isDirectory: entry.isDirectory() }))
}

/**
 * Compiler output under every package's `src/`.
 *
 * @param {string} repoPath the workspace root.
 * @return {string[]} offending files as workspace-relative paths.
 */
export function findSourceOutput(repoPath) {
  const packagesPath = path.join(repoPath, PackagesSubpath)
  return listEntries(packagesPath)
    .filter(({ isDirectory }) => isDirectory)
    .flatMap(({ name: packageName }) =>
      listFiles(path.join(packagesPath, packageName, "src"), [...IgnoredEntries, "node_modules"])
    )
    .map(file => path.relative(repoPath, file).split(path.sep).join("/"))
    .filter(file => SourceOutputPattern.test(file) && !SourceOutputAllowlist.includes(file))
}

/**
 * A tsconfig's `compilerOptions.outDir`, read as tsc reads the file: comments and trailing commas
 * are allowed (`ts.readConfigFile`), and `extends` is not followed (the package's own value).
 *
 * @param {string} file the tsconfig file.
 * @return {string | undefined} the outDir, or undefined when the file sets none.
 * @throws {Error} when the file cannot be read or parsed, with tsc's message.
 */
export function readOutDir(file) {
  const { config, error } = ts.readConfigFile(file, ts.sys.readFile)
  if (error != null)
    throw new Error(`${file}: ${ts.flattenDiagnosticMessageText(error.messageText, "\n")}`)
  return config.compilerOptions?.outDir
}

/**
 * Package tsconfig files whose `outDir` is not one of {@link OutDirPattern}.
 *
 * @param {string} repoPath the workspace root.
 * @return {string[]} each offender as `<workspace-relative tsconfig>: outDir <value>`.
 */
export function findOutDirViolations(repoPath) {
  const packagesPath = path.join(repoPath, PackagesSubpath)
  return listEntries(packagesPath)
    .filter(({ isDirectory }) => isDirectory)
    .flatMap(({ name: packageName }) =>
      listEntries(path.join(packagesPath, packageName))
        .filter(({ name, isDirectory }) => !isDirectory && TsconfigPattern.test(name))
        .map(({ name }) => path.join(packagesPath, packageName, name))
    )
    .map(file => ({ file, outDir: readOutDir(file) }))
    .filter(({ outDir }) => outDir != null && !OutDirPattern.test(outDir))
    .map(({ file, outDir }) => `${path.relative(repoPath, file).split(path.sep).join("/")}: outDir ${outDir}`)
}

/**
 * Every root entry outside the standard, compiler output under `src/`, and tsconfig output
 * outside `lib/{esm,cjs,test,node}`.
 *
 * @param {string} repoPath the workspace root.
 * @return {string[]} offending entries as workspace-relative paths, sorted.
 */
export function findViolations(repoPath) {
  const rootViolations = listEntries(repoPath, [...IgnoredEntries, ...RootGeneratedEntries])
      .filter(({ name, isDirectory }) =>
        isDirectory
          ? !RootDirectories.includes(name)
          : !RootFiles.includes(name)
      )
      .map(({ name, isDirectory }) => `${name}${isDirectory ? "/" : ""}`),
    packagesPath = path.join(repoPath, PackagesSubpath),
    packageViolations = listEntries(packagesPath)
      .filter(({ isDirectory }) => isDirectory)
      .flatMap(({ name: packageName }) =>
        listEntries(path.join(packagesPath, packageName))
          .filter(({ name, isDirectory }) =>
            isDirectory
              ? !PackageDirectories.includes(name)
              : !PackageFilePatterns.some(pattern => pattern.test(name))
          )
          .map(
            ({ name, isDirectory }) =>
              `${PackagesSubpath}/${packageName}/${name}${isDirectory ? "/" : ""}`
          )
      )
  return [
    ...rootViolations,
    ...packageViolations,
    ...findSourceOutput(repoPath),
    ...findOutDirViolations(repoPath)
  ].sort()
}

/** Parse flags and report violations. */
function main() {
  const { "repo-path": repoPathOption = RepoPath } = parseArguments(Flags),
    repoPath = path.resolve(repoPathOption)
  if (!fs.existsSync(path.join(repoPath, PackagesSubpath)))
    throw new UsageError(`no ${PackagesSubpath}/ under ${repoPath}`)
  const violations = findViolations(repoPath)
  if (violations.length === 0) {
    echo(`package layout: ${repoPath} is clean`)
    return ExitCode.success
  }
  echo(
    chalk.red(
      `package layout: ${violations.length} entr${violations.length === 1 ? "y is" : "ies are"} outside the standard`
    )
  )
  violations.forEach(violation => echo(chalk.red(`  ${violation}`)))
  echo(
    "tool config → etc/<tool>/, helper scripts → scripts/, suites → tests/, static app files → resources/; compiler output belongs in lib/{esm,cjs,test,node}/ (tsconfig outDir) or dist/, never src/"
  )
  return ExitCode.violation
}

if (isEntryScript(import.meta.filename)) {
  await runMain(main)
}
