const config = {
  displayName: "code-search-local-webapp",
  // DOM suites opt in per file with the `@jest-environment jest-fixed-jsdom` docblock.
  testEnvironment: "node",
  roots: ["<rootDir>/tests"],
  testMatch: ["**/*.test.ts", "**/*.test.tsx"],
  testPathIgnorePatterns: ["/tests/e2e/"],
  setupFilesAfterEnv: ["<rootDir>/tests/jest.afterEnv.ts"],
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
  extensionsToTreatAsEsm: [".ts", ".tsx"],
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      { tsconfig: "<rootDir>/tsconfig.jest.json", useESM: true }
    ]
  },
  // Ordered: jest takes the FIRST matching pattern. Assets are replaced before the package alias
  // and `.js`-strip patterns can resolve the real file.
  moduleNameMapper: {
    "\\.css$": "<rootDir>/tests/__mocks__/styleMock.ts",
    "^@code-search-local/code-search-local-webapp$": "<rootDir>/src/index.ts",
    "^@code-search-local/code-search-local-webapp/(.*?)(\\.js)?$":
      "<rootDir>/src/$1",
    "^@code-search-local/code-search-local-api$":
      "<rootDir>/../code-search-local-api/src/index.ts",
    "^@code-search-local/code-search-local-api/(.*?)(\\.js)?$":
      "<rootDir>/../code-search-local-api/src/$1",
    "^(\\.{1,2}/.*)\\.js$": "$1"
  }
}

export default config
