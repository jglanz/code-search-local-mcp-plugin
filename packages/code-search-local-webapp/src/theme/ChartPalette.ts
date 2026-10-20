/**
 * Colours of data marks (meter fills, inline bars), kept apart from the UI's `primary`: a data
 * mark needs a mid-lightness, saturated hue in BOTH schemes, while the dark `primary` is a light
 * tint for text. Each scheme's pair is validated with the dataviz palette validator: the accent
 * clears 3:1 against the scheme's surface and against its own track.
 */
export interface ChartPalette {
  /** Fill of the measured part of a mark (hits, appearances). */
  accent: string

  /** The unfilled remainder of a meter: a step of the accent's own ramp that recedes. */
  track: string
}

declare module "@mui/material/styles" {
  interface Palette {
    /** Data-mark colours of the active scheme. */
    chart: ChartPalette
  }

  interface PaletteOptions {
    /** Data-mark colours of a scheme. */
    chart?: ChartPalette
  }
}
