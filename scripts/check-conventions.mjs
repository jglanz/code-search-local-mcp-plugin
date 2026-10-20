#!/usr/bin/env node
/**
 * Enforce the STYLE.md conventions ESLint cannot express syntactically, using the TypeScript
 * compiler API over the `src/` and `tests/` of every TypeScript package (a package whose root
 * holds `tsconfig.json`; the Python service package has none, and the sample `.ts` sources its
 * tests index are test data, not workspace code):
 *
 *   import-order      groups in order node: → external → @code-search-local/* → relative, a blank line
 *                     between groups
 *   barrel-shape      index.ts holds only `export * from "./X.js"` / `"./dir/index.js"` lines
 *   directory-naming  directories are kebab-case (`__mocks__` excepted)
 *   file-naming       a PascalCase file exports a symbol of the same name; a class or enum
 *                     lives in a PascalCase file named after it; a .tsx component file is
 *                     PascalCase (main.tsx, index.ts and *.d.ts excepted)
 *   jsdoc             every exported declaration, exported namespace member, public class member
 *                     and interface field under src/ carries a JSDoc comment
 *   one-component     a .tsx file under src/ exports at most one component
 *
 * Usage:
 *   ./scripts/check-conventions.mjs [--repo-path <dir>]
 *
 * Options:
 *   --repo-path <dir>   workspace to check (default: this workspace)
 *
 * Exit codes:
 *   0  no violations
 *   1  violations found (each printed as path:line rule message)
 *   2  usage error, or the repo path has no packages/ directory (a mistyped --repo-path)
 *
 * Examples:
 *   ./scripts/check-conventions.mjs
 *   ./scripts/check-conventions.mjs --repo-path scripts/tests/fixtures/conventions
 */

import ts from "typescript"
import { chalk, echo, fs, path } from "zx"

import { ExitCode, RepoPath, UsageError, isEntryScript, listFiles, parseArguments, runMain } from "./common/cli-common.mjs"

/** Flag kinds this script accepts. */
const Flags = Object.freeze({ strings: ["repo-path"] })

/** Rule identifiers (printed with every violation). */
export const Rule = Object.freeze({
  importOrder: "import-order",
  barrelShape: "barrel-shape",
  directoryNaming: "directory-naming",
  fileNaming: "file-naming",
  jsdoc: "jsdoc",
  oneComponent: "one-component"
})

/**
 * Directories never entered: dependencies, compiler and bundler output, and `generated/` (code a
 * build generates from a source document, such as the API package's OpenAPI schemas, follows its
 * generator's conventions; the document is what gets reviewed).
 */
const SkippedDirectories = Object.freeze(["node_modules", "lib", "dist", "generated"])

/** Directory names exempt from kebab-case. */
const DirectoryNameExceptions = Object.freeze(["__mocks__"])

/** Import groups, in required order. */
const ImportGroup = Object.freeze({ builtin: 0, external: 1, workspace: 2, relative: 3 })

/** Scope of workspace packages. */
const WorkspaceScope = "@code-search-local/"

/** The file whose presence at a package root makes it a TypeScript package. */
const PackageTsconfigFile = "tsconfig.json"

/** A PascalCase name (class/type/component files, components); loosening it admits other file names. */
const PascalCasePattern = /^[A-Z][A-Za-z0-9]*$/

/** A kebab-case directory name; loosening it admits other directory names. */
const KebabCasePattern = /^[a-z0-9]+(-[a-z0-9]+)*$/

/** The only barrel specifiers allowed: `./X.js` or `./dir/index.js`. */
const BarrelSpecifierPattern = /^\.\/([A-Za-z0-9]+\.js|[a-z0-9-]+\/index\.js)$/

/** Files checked at all; anything else under src/ and tests/ is ignored. */
const SourceFilePattern = /\.(ts|tsx)$/

/** The extension (with `.test` for tests) stripped to get the stem a PascalCase file must export. */
const TestStemPattern = /\.(test\.)?(ts|tsx)$/

/** A blank line (possibly holding only whitespace): the required separator between import groups. */
const BlankLinePattern = /\n\s*\n/

/**
 * Every checked source file: `packages/<pkg>/{src,tests}/**.{ts,tsx}` of every TypeScript
 * package (one holding {@link PackageTsconfigFile}), except declarations.
 *
 * @param {string} repoPath the workspace root.
 * @return {string[]} absolute paths.
 * @throws {UsageError} when `repoPath` has no `packages/` directory (nothing to check means the
 *   path is wrong, never that the workspace is clean).
 */
export function listSourceFiles(repoPath) {
  const packagesPath = path.join(repoPath, "packages")
  if (!fs.existsSync(packagesPath)) throw new UsageError(`${repoPath} has no packages/ directory — is --repo-path the workspace root?`)
  return fs
    .readdirSync(packagesPath)
    .filter(packageName => fs.existsSync(path.join(packagesPath, packageName, PackageTsconfigFile)))
    .flatMap(packageName =>
      ["src", "tests"].flatMap(area => listFiles(path.join(packagesPath, packageName, area), SkippedDirectories))
    )
    .filter(file => SourceFilePattern.test(file) && !file.endsWith(".d.ts"))
}

/**
 * Classify an import specifier.
 *
 * @param {string} specifier the module specifier.
 * @return {number} its {@link ImportGroup}.
 */
function classifyImport(specifier) {
  if (specifier.startsWith("node:")) return ImportGroup.builtin
  if (specifier.startsWith(WorkspaceScope)) return ImportGroup.workspace
  if (specifier.startsWith(".")) return ImportGroup.relative
  return ImportGroup.external
}

/**
 * Whether a node is exported.
 *
 * @param {ts.Node} node the node.
 * @return {boolean} true with an `export` modifier.
 */
function isExported(node) {
  return (ts.getCombinedModifierFlags(node) & ts.ModifierFlags.Export) !== 0
}

/**
 * Whether a node has a JSDoc comment.
 *
 * @param {ts.Node} node the node.
 * @return {boolean} true when a `/** … *\/` comment is attached.
 */
function hasJsDoc(node) {
  return (node.jsDoc ?? []).length > 0
}

/**
 * The declared name of a statement, when it has one.
 *
 * @param {ts.Statement} statement the statement.
 * @return {string[]} declared names (several for a multi-declarator variable statement).
 */
function declaredNames(statement) {
  if (ts.isVariableStatement(statement))
    return statement.declarationList.declarations.map(declaration => declaration.name.getText())
  return statement.name == null ? [] : [statement.name.getText()]
}

/**
 * Check one file.
 *
 * @param {string} repoPath the workspace root (paths are reported relative to it).
 * @param {string} file the absolute file path.
 * @return {{ file: string, line: number, rule: string, message: string }[]} violations.
 */
export function checkFile(repoPath, file) {
  const text = fs.readFileSync(file, "utf8"),
    relativeFile = path.relative(repoPath, file),
    sourceFile = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS),
    violations = [],
    report = (node, rule, message) =>
      violations.push({
        file: relativeFile,
        line: node == null ? 1 : sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile)).line + 1,
        rule,
        message
      }),
    segments = relativeFile.split(path.sep),
    areaIndex = segments.findIndex(segment => segment === "src" || segment === "tests"),
    area = segments[areaIndex],
    directories = segments.slice(areaIndex + 1, -1),
    basename = segments.at(-1),
    stem = basename.replace(TestStemPattern, ""),
    isSource = area === "src"

  directories
    .filter(directory => !DirectoryNameExceptions.includes(directory) && !KebabCasePattern.test(directory))
    .forEach(directory => report(null, Rule.directoryNaming, `directory "${directory}" is not kebab-case`))

  checkImportOrder(sourceFile, text, report)
  if (basename === "index.ts") checkBarrel(sourceFile, report)
  else if (isSource && basename !== "main.tsx") checkFileNaming(sourceFile, stem, basename, report)
  if (isSource && basename !== "index.ts") checkJsDoc(sourceFile, report)
  if (isSource && basename.endsWith(".tsx")) checkOneComponent(sourceFile, report)
  return violations
}

/**
 * import-order: groups ascend, and a blank line separates two groups.
 *
 * @param {ts.SourceFile} sourceFile the file.
 * @param {string} text its text.
 * @param {Function} report the violation sink.
 */
function checkImportOrder(sourceFile, text, report) {
  const imports = sourceFile.statements.filter(ts.isImportDeclaration)
  imports.slice(1).forEach((current, index) => {
    const previous = imports[index],
      previousGroup = classifyImport(previous.moduleSpecifier.text),
      currentGroup = classifyImport(current.moduleSpecifier.text),
      between = text.slice(previous.getEnd(), current.getStart(sourceFile))
    if (currentGroup < previousGroup)
      report(current, Rule.importOrder, `"${current.moduleSpecifier.text}" must come before "${previous.moduleSpecifier.text}" (node: → external → @code-search-local/* → relative)`)
    else if (currentGroup !== previousGroup && !BlankLinePattern.test(between))
      report(current, Rule.importOrder, `blank line required between import groups before "${current.moduleSpecifier.text}"`)
  })
}

/**
 * barrel-shape: only `export * from "./X.js"` / `"./dir/index.js"`.
 *
 * @param {ts.SourceFile} sourceFile the file.
 * @param {Function} report the violation sink.
 */
function checkBarrel(sourceFile, report) {
  sourceFile.statements.forEach(statement => {
    const valid =
      ts.isExportDeclaration(statement) &&
      statement.exportClause == null &&
      !statement.isTypeOnly &&
      statement.moduleSpecifier != null &&
      BarrelSpecifierPattern.test(statement.moduleSpecifier.text)
    if (!valid) report(statement, Rule.barrelShape, `index.ts may only contain export * from "./X.js" or "./dir/index.js" lines`)
  })
}

/**
 * file-naming: PascalCase file ↔ same-named export; class/enum only in its own PascalCase file;
 * a component (.tsx) file is PascalCase.
 *
 * @param {ts.SourceFile} sourceFile the file.
 * @param {string} stem the file name without extension.
 * @param {string} basename the file name.
 * @param {Function} report the violation sink.
 */
function checkFileNaming(sourceFile, stem, basename, report) {
  const exported = sourceFile.statements.filter(isExported),
    exportedNames = exported.flatMap(declaredNames),
    pascalFile = PascalCasePattern.test(stem)
  if (basename.endsWith(".tsx") && !pascalFile)
    report(null, Rule.fileNaming, `component file "${basename}" must be PascalCase`)
  if (pascalFile && !exportedNames.includes(stem))
    report(null, Rule.fileNaming, `"${basename}" is PascalCase but exports no symbol named ${stem}`)
  exported
    .filter(statement => ts.isClassDeclaration(statement) || ts.isEnumDeclaration(statement))
    .filter(statement => statement.name != null && statement.name.text !== stem)
    .forEach(statement =>
      report(statement, Rule.fileNaming, `${statement.name.text} must live in its own file ${statement.name.text}${path.extname(basename)}`)
    )
}

/**
 * jsdoc: exported declarations, exported namespace members, public class members, interface fields.
 *
 * @param {ts.SourceFile} sourceFile the file.
 * @param {Function} report the violation sink.
 */
function checkJsDoc(sourceFile, report) {
  const checkStatements = statements =>
    statements.forEach(statement => {
      const exported = isExported(statement),
        documentable =
          ts.isFunctionDeclaration(statement) ||
          ts.isClassDeclaration(statement) ||
          ts.isInterfaceDeclaration(statement) ||
          ts.isTypeAliasDeclaration(statement) ||
          ts.isEnumDeclaration(statement) ||
          ts.isVariableStatement(statement) ||
          ts.isModuleDeclaration(statement)
      if (exported && documentable && !hasJsDoc(statement))
        report(statement, Rule.jsdoc, `exported ${declaredNames(statement).join(", ") || "declaration"} has no JSDoc`)
      if (ts.isInterfaceDeclaration(statement))
        statement.members
          .filter(member => !hasJsDoc(member))
          .forEach(member => report(member, Rule.jsdoc, `interface ${statement.name.text} field ${member.name?.getText() ?? "(index)"} has no JSDoc`))
      if (ts.isClassDeclaration(statement) && exported)
        statement.members
          .filter(member => ts.isMethodDeclaration(member) || ts.isPropertyDeclaration(member) || ts.isGetAccessor(member))
          .filter(member => {
            const flags = ts.getCombinedModifierFlags(member)
            return (flags & (ts.ModifierFlags.Private | ts.ModifierFlags.Protected)) === 0 && !member.name.getText().startsWith("#")
          })
          .filter(member => !hasJsDoc(member))
          .forEach(member => report(member, Rule.jsdoc, `${statement.name?.text}.${member.name.getText()} has no JSDoc`))
      if (ts.isModuleDeclaration(statement) && exported && statement.body != null && ts.isModuleBlock(statement.body))
        checkStatements(statement.body.statements)
    })
  checkStatements(sourceFile.statements)
}

/**
 * one-component: a .tsx file exports at most one PascalCase function component.
 *
 * @param {ts.SourceFile} sourceFile the file.
 * @param {Function} report the violation sink.
 */
function checkOneComponent(sourceFile, report) {
  const components = sourceFile.statements
    .filter(isExported)
    .filter(
      statement =>
        (ts.isFunctionDeclaration(statement) && statement.name != null && PascalCasePattern.test(statement.name.text)) ||
        (ts.isVariableStatement(statement) &&
          statement.declarationList.declarations.some(
            declaration =>
              PascalCasePattern.test(declaration.name.getText()) &&
              declaration.initializer != null &&
              (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer))
          ))
    )
  if (components.length > 1)
    report(components[1], Rule.oneComponent, `exports ${components.length} components (${components.flatMap(declaredNames).join(", ")}); one component per .tsx file`)
}

/**
 * Check every source file of a workspace.
 *
 * @param {string} repoPath the workspace root.
 * @param {string[]} [files] the files to check (default: {@link listSourceFiles} of `repoPath`).
 * @return {{ file: string, line: number, rule: string, message: string }[]} all violations.
 */
export function checkConventions(repoPath, files = listSourceFiles(repoPath)) {
  return files.flatMap(file => checkFile(repoPath, file))
}

/** Parse flags and report. */
function main() {
  const { "repo-path": repoPathOption = RepoPath } = parseArguments(Flags),
    repoPath = path.resolve(repoPathOption),
    files = listSourceFiles(repoPath),
    violations = checkConventions(repoPath, files)
  if (violations.length === 0) {
    echo(`conventions: ${files.length} files clean`)
    return ExitCode.success
  }
  violations.forEach(({ file, line, rule, message }) => echo(chalk.red(`${file}:${line} ${rule} ${message}`)))
  echo(chalk.red(`conventions: ${violations.length} violation(s)`))
  return ExitCode.failure
}

if (isEntryScript(import.meta.filename)) {
  await runMain(main)
}
