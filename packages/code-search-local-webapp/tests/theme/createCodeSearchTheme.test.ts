import { describe, expect, it } from "@jest/globals"

import type { CssVarsTheme } from "@mui/material/styles"

import { createCodeSearchTheme } from "@code-search-local/code-search-local-webapp"

describe("createCodeSearchTheme", () => {
  it("uses the documented primary colours, font size and radius with CSS variables", () => {
    const theme = createCodeSearchTheme() as unknown as CssVarsTheme
    expect(theme.colorSchemes.light.palette.primary.main).toBe(
      createCodeSearchTheme.PrimaryLight
    )
    expect(theme.colorSchemes.dark.palette.primary.main).toBe(
      createCodeSearchTheme.PrimaryDark
    )
    expect(theme.typography.fontSize).toBe(createCodeSearchTheme.BaseFontSize)
    expect(theme.shape.borderRadius).toBe(createCodeSearchTheme.BorderRadius)
    expect(theme.vars).toBeDefined()
  })

  it("gives each colour scheme its own validated data-mark pair", () => {
    const theme = createCodeSearchTheme() as unknown as CssVarsTheme
    expect(theme.colorSchemes.light.palette.chart).toEqual(
      createCodeSearchTheme.ChartLight
    )
    expect(theme.colorSchemes.dark.palette.chart).toEqual(
      createCodeSearchTheme.ChartDark
    )
    expect(createCodeSearchTheme.ChartLight.accent).not.toBe(
      createCodeSearchTheme.ChartDark.accent
    )
  })

  it("returns a fresh theme per call, so one app never mutates another's", () => {
    expect(createCodeSearchTheme()).not.toBe(createCodeSearchTheme())
  })
})
