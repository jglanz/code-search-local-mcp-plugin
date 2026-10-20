/**
 * Proves each check-conventions rule fires on its fixture (fixtures/conventions) and that a
 * conforming file and barrel produce no violation.
 */
import assert from "node:assert/strict"
import path from "node:path"
import { describe, it } from "node:test"

import { Rule, checkConventions, listSourceFiles } from "../check-conventions.mjs"
import { UsageError } from "../common/cli-common.mjs"

const FixturePath = path.join(import.meta.dirname, "fixtures", "conventions"),
  violations = checkConventions(FixturePath),
  SourcePrefix = "packages/fx/src/"

/**
 * The rules reported for one fixture file.
 *
 * @param {string} file path under packages/fx/src/.
 * @return {string[]} rule ids, sorted.
 */
function rulesFor(file) {
  return violations
    .filter(violation => violation.file === `${SourcePrefix}${file}`)
    .map(({ rule }) => rule)
    .sort()
}

describe("check-conventions rules", () => {
  it("import-order: wrong group order and a missing blank line", () => {
    assert.deepEqual(rulesFor("bad-imports/importOrder.ts"), [Rule.importOrder, Rule.importOrder])
    assert.deepEqual(rulesFor("bad-imports/missingBlankLine.ts"), [Rule.importOrder])
  })

  it("directory-naming: a PascalCase directory", () => {
    assert.deepEqual(rulesFor("BadDir/thing.ts"), [Rule.directoryNaming])
  })

  it("barrel-shape: a named re-export in index.ts", () => {
    assert.deepEqual(rulesFor("barrel/index.ts"), [Rule.barrelShape])
  })

  it("file-naming: PascalCase file without its symbol, class in a topic file, lower-case component file", () => {
    assert.deepEqual(rulesFor("Widget.ts"), [Rule.fileNaming])
    assert.deepEqual(rulesFor("helpers.ts"), [Rule.fileNaming])
    assert.deepEqual(rulesFor("component.tsx"), [Rule.fileNaming])
    assert.deepEqual(rulesFor("ExtraEnum.ts"), [Rule.fileNaming])
  })

  it("jsdoc: an undocumented export and an undocumented interface field", () => {
    assert.deepEqual(rulesFor("Undocumented.ts"), [Rule.jsdoc, Rule.jsdoc])
  })

  it("one-component: two components in one .tsx", () => {
    assert.deepEqual(rulesFor("TwoComponents.tsx"), [Rule.oneComponent])
  })

  it("a conforming file and barrel report nothing", () => {
    assert.deepEqual(rulesFor("Clean.ts"), [])
    assert.deepEqual(rulesFor("index.ts"), [])
  })
})

describe("checkConventions", () => {
  it("checks exactly the files it is given", () => {
    const files = listSourceFiles(FixturePath).filter(file => file.endsWith(`${path.sep}Clean.ts`))
    assert.equal(files.length, 1)
    assert.deepEqual(checkConventions(FixturePath, files), [])
  })

  it("checks a package with a tsconfig.json and skips one without (the Python package's sample sources)", () => {
    const files = listSourceFiles(FixturePath)
    assert.ok(files.some(file => file.includes(`${path.sep}packages${path.sep}fx${path.sep}`)))
    assert.equal(
      files.some(file => file.includes(`${path.sep}packages${path.sep}py${path.sep}`)),
      false
    )
    assert.deepEqual(
      violations.filter(({ file }) => file.startsWith("packages/py/")),
      []
    )
  })

  it("skips generated/ directories (generated code follows its generator's conventions)", () => {
    assert.equal(
      listSourceFiles(FixturePath).some(file => file.includes(`${path.sep}generated${path.sep}`)),
      false
    )
    assert.deepEqual(rulesFor("generated/apiSchemas.ts"), [])
  })

  it("is a usage error for a path without packages/ (a mistyped --repo-path)", () => {
    assert.throws(() => checkConventions(path.join(FixturePath, "packages")), UsageError)
  })
})
