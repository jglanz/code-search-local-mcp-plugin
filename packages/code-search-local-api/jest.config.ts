const config = {
  displayName: "code-search-local-api",
  testEnvironment: "node",
  roots: ["<rootDir>/tests"],
  testMatch: ["**/*.test.ts"],
  // TypeScript first: a stray compiler emit (`X.js` next to `X.ts`) must never shadow the source
  // the `.js`-strip mapper resolves (check-package-layout also rejects such emits in src/).
  moduleFileExtensions: [
    "ts",
    "tsx",
    "js",
    "mjs",
    "cjs",
    "jsx",
    "json",
    "node"
  ],
  extensionsToTreatAsEsm: [".ts"],
  transform: {
    "^.+\\.ts$": [
      "ts-jest",
      { tsconfig: "<rootDir>/tsconfig.jest.json", useESM: true }
    ]
  },
  // Ordered: jest takes the FIRST matching pattern.
  moduleNameMapper: {
    "^@code-search-local/code-search-local-api$": "<rootDir>/src/index.ts",
    "^@code-search-local/code-search-local-api/(.*?)(\\.js)?$":
      "<rootDir>/src/$1",
    "^(\\.{1,2}/.*)\\.js$": "$1"
  }
}

export default config
