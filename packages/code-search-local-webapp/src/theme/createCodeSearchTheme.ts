import { createTheme, type Theme } from "@mui/material/styles"

import type { ChartPalette } from "./ChartPalette.js"

/**
 * The app theme: light and dark colour schemes switched by the OS preference (CSS variables,
 * `prefers-color-scheme`), a dense typography scale for tables of projects and paths.
 *
 * @returns the MUI theme.
 */
export function createCodeSearchTheme(): Theme {
  return createTheme({
    cssVariables: { colorSchemeSelector: "media" },
    colorSchemes: {
      light: {
        palette: {
          primary: { main: createCodeSearchTheme.PrimaryLight },
          chart: createCodeSearchTheme.ChartLight
        }
      },
      dark: {
        palette: {
          primary: { main: createCodeSearchTheme.PrimaryDark },
          chart: createCodeSearchTheme.ChartDark
        }
      }
    },
    typography: { fontSize: createCodeSearchTheme.BaseFontSize },
    shape: { borderRadius: createCodeSearchTheme.BorderRadius }
  })
}

/** Theme constants. */
export namespace createCodeSearchTheme {
  /** Light-scheme primary; changing it recolours primary buttons, links, focused inputs and primary chips. */
  export const PrimaryLight = "#2f6fb0"

  /** Dark-scheme primary (lighter for contrast); changing it recolours the same elements in dark mode. */
  export const PrimaryDark = "#8bb8e8"

  /**
   * Light-scheme data marks: blue 450 on blue 100 of the dataviz reference ramp. Changing either
   * recolours every meter and inline bar; re-run the palette validator against the light surface.
   */
  export const ChartLight: ChartPalette = {
    accent: "#2a78d6",
    track: "#cde2fb"
  }

  /**
   * Dark-scheme data marks: blue 400 on blue 700 of the same ramp (the track recedes into the
   * dark surface). Changing either recolours every meter and inline bar in dark mode.
   */
  export const ChartDark: ChartPalette = { accent: "#3987e5", track: "#0d366b" }

  /** Base font size in px; every typography variant scales from it. */
  export const BaseFontSize = 14

  /** Corner radius of cards, chips and inputs in px. */
  export const BorderRadius = 8
}
