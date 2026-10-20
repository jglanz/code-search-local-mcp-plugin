/**
 * Shared webpack configuration for the webapp (dev and prod layer on top).
 *
 * - TypeScript: ts-loader in transpileOnly mode (type-checking is `tsc -b`); no babel/swc —
 *   swc mis-compiles companion namespaces.
 * - The Python service serves the bundle under `/ui/`, so every asset URL carries that prefix
 *   ({@link PublicPath}); the service has no Node side, so there is no server bundle.
 */
import { createRequire } from "node:module"
import path from "node:path"

import HtmlWebpackPlugin from "html-webpack-plugin"

/** This package's root. */
export const PackagePath = path.resolve(import.meta.dirname, "..", "..")

/** Resolves loaders from THIS package (never from the importing process's cwd). */
const moduleRequire = createRequire(import.meta.url)

/**
 * Bundle output directory. The service serves it from a source checkout (and wheel builds copy
 * it), so moving it needs the service's asset lookup to move too.
 */
export const OutputPath = path.join(PackagePath, "dist")

/** The bundle entry, relative to this package (both dev and prod configs start here). */
export const EntrySubpath = "./src/main.tsx"

/**
 * URL prefix of every emitted asset and of the SPA itself: the service's webapp endpoint plus a
 * trailing slash. It must equal `AppRoutePaths.Basename` + `/` (the router's basename);
 * `AppRoutePaths.test` fails when they differ.
 */
export const PublicPath = "/ui/"

/** The HTML page html-webpack-plugin emits at the root of {@link OutputPath}. */
export const IndexHtmlFile = "index.html"

/** The page template (mount element and title). */
export const TemplatePath = path.join(PackagePath, "resources", IndexHtmlFile)

/** The workspace root (ts-loader's root directory: the bundle compiles sources of two packages). */
export const WorkspacePath = path.resolve(PackagePath, "..", "..")

/**
 * The API package's source, compiled into the bundle (the same view jest and `tsconfig.app.json`
 * have), so the bundle never depends on the package's compiled `lib/` being current. Its
 * generated schemas exist once `pnpm run generate` (run by `compile`, `build` and `dev`) has run.
 */
export const ApiSourcePath = path.join(WorkspacePath, "packages", "code-search-local-api", "src")

/** The API package's name, aliased to {@link ApiSourcePath}. */
export const ApiPackageName = "@code-search-local/code-search-local-api"

/** The tsconfig ts-loader compiles with (lib DOM, react-jsx). */
export const AppTsconfigPath = path.join(PackagePath, "tsconfig.app.json")

/**
 * Build the shared configuration.
 *
 * @param {object} options
 * @param {"development"|"production"} options.mode the webpack mode.
 * @param {object[]} [options.tsTransformers] extra `before` transformers for ts-loader (React Refresh in dev).
 * @return {import("webpack").Configuration} the configuration.
 */
export function createCommonWebpackConfig({ mode, tsTransformers = [] }) {
  return {
    mode,
    context: PackagePath,
    target: "web",
    output: {
      path: OutputPath,
      publicPath: PublicPath,
      clean: true
    },
    resolve: {
      extensions: [".tsx", ".ts", ".mjs", ".js"],
      extensionAlias: { ".js": [".ts", ".tsx", ".js"] },
      alias: {
        [`${ApiPackageName}$`]: path.join(ApiSourcePath, "index.ts"),
        [ApiPackageName]: ApiSourcePath
      }
    },
    module: {
      rules: [
        { test: /\.m?js$/, resolve: { fullySpecified: false } },
        {
          test: /\.tsx?$/,
          exclude: /node_modules/,
          use: {
            loader: moduleRequire.resolve("ts-loader"),
            options: {
              transpileOnly: true,
              configFile: AppTsconfigPath,
              // Project-reference settings (rootDir, composite, declarations) belong to `tsc -b`,
              // not to the bundle, which also compiles the API package's source.
              compilerOptions: {
                rootDir: WorkspacePath,
                composite: false,
                declaration: false,
                declarationMap: false
              },
              getCustomTransformers: () => ({ before: tsTransformers })
            }
          }
        },
        {
          test: /\.css$/,
          use: [moduleRequire.resolve("style-loader"), moduleRequire.resolve("css-loader")]
        }
      ]
    },
    plugins: [
      new HtmlWebpackPlugin({
        template: TemplatePath,
        filename: IndexHtmlFile
      })
    ]
  }
}
