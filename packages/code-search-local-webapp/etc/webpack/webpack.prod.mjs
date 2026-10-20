/**
 * Production configuration (`pnpm build`): content-hashed assets in `dist/`, served by the
 * Python service under `/ui/`.
 */
import { EntrySubpath, createCommonWebpackConfig } from "./webpack.common.mjs"

/**
 * Build the production configuration.
 *
 * @return {import("webpack").Configuration} the configuration.
 */
export function createProdWebpackConfig() {
  const common = createCommonWebpackConfig({ mode: "production" })
  return {
    ...common,
    entry: EntrySubpath,
    devtool: "source-map",
    output: { ...common.output, filename: "assets/[name].[contenthash].js" },
    performance: { hints: false }
  }
}

export default createProdWebpackConfig()
