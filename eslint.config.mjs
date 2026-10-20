// =============================================================================
// code-search-local workspace eslint — mechanical enforcement of STYLE.md.
//
// Two layers:
//  1. REFERENCE: the rule set of the wire-tools-ts eslint config, re-written (same
//     bans, same overrides, same carve-outs).
//  2. EXTENSION: documented STYLE.md rules the reference leaves to review, made
//     mechanical here (default exports, extensionless relative specifiers, for
//     loops, React.FC, styled(), exported loggers, `if (x.success)`, lodash vs
//     lodash-es, MUI root imports, inline disable directives).
//
// Formatting belongs to prettier; eslint-config-prettier is applied LAST.
// The tsconfig compiles with `strictNullChecks: false`; `eqeqeq` allows `!= null`.
// Syntactic rules only. `error` means the class is banned everywhere — no debt
// list, no per-file exemption, and (noInlineConfig) no inline disable comment.
// =============================================================================
import eslint from "@eslint/js"
import tseslint from "typescript-eslint"
import prettier from "eslint-config-prettier"

import { CodeSearchLocalPlugin } from "./etc/eslint/codeSearchLocalPlugin.mjs"

// ---------------------------------------------------------------------------
// REFERENCE bans (wire-tools-ts)
// ---------------------------------------------------------------------------

const BanSwitch = {
  selector: "SwitchStatement",
  message: "Use match() from ts-pattern (STYLE.md 'match() over switch')."
}

const BanInlineIife = {
  selector:
    "CallExpression[callee.type='ArrowFunctionExpression'], CallExpression[callee.type='FunctionExpression']",
  message: "No inline IIFEs — extract a named local helper (STYLE.md 'Extracted helpers')."
}

const BanNullUnionReturn = {
  selector: ":function > TSTypeAnnotation.returnType TSUnionType > TSNullKeyword",
  message:
    "No `| null` return-type ceremony — strictNullChecks is OFF; write the plain type, callers guard with `!= null`."
}

const BanInlineTypeLiteral = {
  selector: "TSTypeLiteral",
  message: "No inline object types — declare a named interface/type."
}

const BanPickParameter = {
  selector:
    ":matches(FunctionDeclaration, FunctionExpression, ArrowFunctionExpression, TSDeclareFunction, TSEmptyBodyFunctionExpression, TSMethodSignature, TSFunctionType) > :matches(Identifier, ObjectPattern, ArrayPattern, RestElement, AssignmentPattern, TSParameterProperty) TSTypeReference[typeName.name='Pick']",
  message:
    'No Pick<T,K> parameter contracts — one field → indexed access (T["field"]), several optional fields → Partial<T>, otherwise T.'
}

const BanStringLiteralUnion = {
  selector: "TSUnionType > TSLiteralType > Literal[raw=/^[\"']/]",
  message:
    "No hand-written string-literal unions — declare the identity enum, or derive the union from one (`${Enum}`)."
}

const BanAsOptionAwait = {
  selector: "CallExpression[callee.name='asOption'] > AwaitExpression",
  message: "Never asOption(await …) — bind the awaited value and use plain statements."
}

const BanMemberCoalesceDeclarator = {
  selector:
    "VariableDeclarator > LogicalExpression.init[operator='??'] > MemberExpression.left[computed=false]",
  message:
    "Destructure with a default — `const { member: local = Default } = obj` — not `const local = obj.member ?? Default`."
}

const BanErrorMessageRestring = {
  selector:
    "NewExpression[callee.name=/^(Error|TypeError|RangeError|EvalError|SyntaxError|URIError)$/] :matches(CallExpression[callee.name='toMessage'], MemberExpression[property.name=/^(message|stack)$/][object.name=/^(err|error|e|ex|cause|reason)$/])",
  message: "Don't restring a caught error into a bare Error — use NestedError(message, { cause, context })."
}

const BanBareErrorInHandler = {
  selector:
    "CallExpression[callee.property.name=/^(mapLeft|ifLeft|catch|recoverWith|onFailure)$/] NewExpression[callee.name=/^(Error|TypeError|RangeError|EvalError|SyntaxError|URIError)$/][arguments.length<2]",
  message:
    "A bare Error in an error handler (mapLeft/ifLeft/catch/recoverWith/onFailure) swallows the handled error — throw a NestedError with { cause }."
}

const ReferenceBans = [
  BanSwitch,
  BanInlineIife,
  BanNullUnionReturn,
  BanInlineTypeLiteral,
  BanPickParameter,
  BanStringLiteralUnion,
  BanAsOptionAwait,
  BanMemberCoalesceDeclarator,
  BanErrorMessageRestring,
  BanBareErrorInHandler
]

// ---------------------------------------------------------------------------
// EXTENSION bans (STYLE.md rules made mechanical)
// ---------------------------------------------------------------------------

const BanDefaultExport = {
  selector: "ExportDefaultDeclaration, ExportSpecifier[exported.name='default']",
  message: "No default exports — export named symbols (STYLE.md 'Files')."
}

const BanExtensionlessRelativeSpecifier = {
  selector:
    ":matches(ImportDeclaration, ExportAllDeclaration, ExportNamedDeclaration, ImportExpression) > Literal.source[value=/^\\.{1,2}\\//]:not([value=/\\.(js|mjs|json|css|mdx)$/])",
  message: "Relative import/export specifiers end in `.js` (STYLE.md 'Files')."
}

const BanForLoops = {
  selector: "ForStatement, ForInStatement, ForOfStatement[await=false]",
  message: "Use forEach/map/filter/reduce — `for await` is allowed only to consume streams (STYLE.md 'Loops')."
}

const BanReactFc = {
  selector:
    "TSTypeReference[typeName.name=/^(FC|FunctionComponent)$/], TSTypeReference[typeName.right.name=/^(FC|FunctionComponent)$/]",
  message: "No React.FC — type the props with an exported XProps interface (STYLE.md 'React')."
}

const BanStyled = {
  selector: "CallExpression[callee.name='styled'], TaggedTemplateExpression[tag.callee.name='styled']",
  message: "Style with `sx` only — never styled() (STYLE.md 'MUI')."
}

const BanExportedLog = {
  selector: "ExportNamedDeclaration > VariableDeclaration > VariableDeclarator[id.name='log']",
  message: "Never `export const log` — every file owns `const log = getLogger(import.meta.url)` (STYLE.md 'Logging')."
}

const BanSuccessBranch = {
  selector:
    "IfStatement > MemberExpression.test[property.name='success'], IfStatement > UnaryExpression.test > MemberExpression[property.name='success']",
  message: "Route safeParse results through Either (SchemaCodec), never `if (result.success)` (STYLE.md 'zod')."
}

const ExtensionBans = [
  BanDefaultExport,
  BanExtensionlessRelativeSpecifier,
  BanForLoops,
  BanReactFc,
  BanStyled,
  BanExportedLog,
  BanSuccessBranch
]

const AllBans = [...ReferenceBans, ...ExtensionBans]

/**
 * Files whose consumers require a default export: tool configs (jest, playwright) and the
 * Playwright global setup/teardown modules (Playwright loads them by default export).
 */
const DefaultExportFiles = [
  "**/jest.config.ts",
  "**/playwright.config.ts",
  "**/etc/playwright/globalSetup.ts",
  "**/etc/playwright/globalTeardown.ts"
]

export default tseslint.config(
  {
    ignores: [
      "**/lib/**",
      "**/dist/**",
      "**/node_modules/**",
      "**/*.d.ts",
      "**/*.js",
      "**/*.cjs",
      "**/*.mjs",
      "**/*.jsx",
      // Code generated by a package build (e.g. the API package's schemas from its OpenAPI
      // document) follows its generator's conventions.
      "packages/*/src/generated/**",
      // Deliberately non-conforming fixtures; scripts/tests/lintRules.test.mjs lints them
      // with ignore patterns off.
      "scripts/tests/fixtures/**",
      // The Python service package: its tests hold sample TypeScript sources the indexer parses,
      // which are test data, not workspace code. Python is linted by `hatch run lint`.
      "packages/code-search-local/**",
      // Agent plugin assets, CI workflows, Python environments and tool/agent state.
      "plugins/**",
      ".github/**",
      ".venv/**",
      ".venvs/**",
      ".omc/**",
      ".remember/**",
      ".test-artifacts/**"
    ]
  },
  {
    linterOptions: { noInlineConfig: true }
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.ts", "**/*.tsx", "**/*.mts"],
    plugins: { "csl-local": CodeSearchLocalPlugin },
    rules: {
      "no-console": "error",
      "csl-local/no-identity-arrow": "error",
      "no-restricted-syntax": ["error", ...AllBans],
      "id-match": ["error", "^(?!require[A-Z]).*$", { properties: false, classFields: false, onlyDeclarations: true }],
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "lodash",
              message: "Use lodash-es — Node's ESM loader rejects named imports from CJS lodash (STYLE.md 'lodash')."
            },
            {
              name: "@mui/material",
              message: "Deep default import per component: `import Box from \"@mui/material/Box\"` (STYLE.md 'MUI')."
            },
            {
              name: "@mui/icons-material",
              message: "Deep default import per icon: `import Add from \"@mui/icons-material/Add\"` (STYLE.md 'MUI')."
            }
          ],
          patterns: [
            {
              group: ["**/src/*", "**/src"],
              message: "No src/ in import specifiers — use the package alias or the barrel."
            },
            {
              group: ["lodash/*"],
              message: "Use lodash-es named imports."
            }
          ]
        }
      ],
      "no-restricted-properties": [
        "error",
        { object: "process", property: "stdout", message: "process.stdout belongs to the logging appenders only." },
        { object: "process", property: "stderr", message: "process.stderr belongs to the logging appenders only." }
      ],
      eqeqeq: ["error", "always", { null: "ignore" }],
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-namespace": "off",
      "@typescript-eslint/no-empty-object-type": "off",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "preserve-caught-error": "error",
      "prefer-const": "error",
      "no-var": "error"
    }
  },
  {
    files: DefaultExportFiles,
    rules: { "no-restricted-syntax": ["error", ...ReferenceBans, ...ExtensionBans.filter(ban => ban !== BanDefaultExport)] }
  },
  {
    // The sanctioned raw-stream homes (reference carve-out) plus — RELAXATION — console
    // for the browser ConsoleAppender, whose sink IS the devtools console.
    files: ["**/logging/*Appender.ts", "**/tests/logging/*Appender.test.ts"],
    rules: { "no-restricted-properties": "off", "no-console": "off" }
  },
  prettier
)
