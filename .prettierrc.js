module.exports = {
  trailingComma: "none",
  tabWidth: 2,
  semi: false,
  singleQuote: false,
  parser: "typescript",
  arrowParens: "avoid",
  quoteProps: "as-needed",
  jsxSingleQuote: false,
  bracketSameLine: false,
  bracketSpacing: true,
  useTabs: false,
  proseWrap: "always",
  overrides: [
    {
      files: "*.md",
      options: { parser: "markdown" }
    },
    {
      files: "*.{yaml,yml}",
      options: { parser: "yaml" }
    }
  ]
}
