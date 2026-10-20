/**
 * Proves every ESLint rule in the STYLE.md conformance matrix FIRES: each fixture under
 * fixtures/lint/ holds one violation class and must produce only its expected rule.
 * Fixtures are excluded from `pnpm lint`; this suite lints them with ignore patterns off.
 */
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, it } from "node:test"

import { ESLint } from "eslint"

import { RepoPath } from "../common/cli-common.mjs"

const FixturesPath = path.join(import.meta.dirname, "fixtures", "lint"),
  ExpectedRules = JSON.parse(readFileSync(path.join(FixturesPath, "expected-rules.json"), "utf8")),
  eslint = new ESLint({ cwd: RepoPath, ignore: false })

/**
 * Lint one fixture.
 *
 * @param {string} fixture the fixture path relative to fixtures/lint.
 * @return {Promise<import("eslint").Linter.LintMessage[]>} its messages.
 */
async function lintFixture(fixture) {
  const [result] = await eslint.lintFiles([path.join(FixturesPath, fixture)])
  return result.messages
}

describe("lint rules fire on their fixtures", () => {
  Object.entries(ExpectedRules).forEach(([fixture, { ruleId, message }]) => {
    it(`${fixture} → ${ruleId}`, async () => {
      const messages = await lintFixture(fixture)
      assert.deepEqual(
        [...new Set(messages.map(({ ruleId: firedRule }) => firedRule))],
        [ruleId],
        `expected exactly [${ruleId}], got ${JSON.stringify(messages.map(({ ruleId: r, message: m }) => `${r}: ${m}`))}`
      )
      if (message != null) assert.ok(messages[0].message.includes(message), messages[0].message)
    })
  })
})

describe("inline disable directives", () => {
  it("an eslint-disable comment warns (failing --max-warnings 0) and the rule still fires", async () => {
    const messages = await lintFixture("eslint-disable.ts"),
      warnings = messages.filter(({ severity }) => severity === 1),
      errors = messages.filter(({ severity }) => severity === 2)
    assert.equal(warnings.length, 1, JSON.stringify(messages))
    assert.match(warnings[0].message, /no effect because you have 'noInlineConfig'/)
    assert.deepEqual(errors.map(({ ruleId }) => ruleId), ["no-console"])
  })
})

describe("tool config default-export exemption", () => {
  it("jest.config.ts may default-export", async () => {
    assert.deepEqual(await lintFixture("config-exempt/jest.config.ts"), [])
  })
})
