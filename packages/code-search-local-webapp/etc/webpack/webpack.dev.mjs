/**
 * Development configuration (`pnpm dev`, `webpack serve`): webpack-dev-server with HMR and React
 * Refresh serves the bundle from memory under `/ui/` and proxies `/api` to the running Python
 * service. There is no Node server of our own, so the dev server is the whole dev stack.
 *
 * Environment:
 *   CODE_SEARCH_WEBAPP_DEV_PORT  port the dev server listens on (default 8100)
 *   CODE_SEARCH_SERVICE_URL      the service `/api` is proxied to (default http://127.0.0.1:8000)
 */
import ReactRefreshPlugin from "@pmmmwh/react-refresh-webpack-plugin"
import ReactRefreshTypeScript from "react-refresh-typescript"

import { EntrySubpath, IndexHtmlFile, PublicPath, createCommonWebpackConfig } from "./webpack.common.mjs"

/** Environment variable holding the dev server's port. */
export const DevPortVariable = "CODE_SEARCH_WEBAPP_DEV_PORT"

/** Port the dev server listens on when {@link DevPortVariable} is unset. */
export const DefaultDevPort = 8100

/** Environment variable holding the URL of the service `/api` requests are proxied to. */
export const ServiceUrlVariable = "CODE_SEARCH_SERVICE_URL"

/** The service URL when {@link ServiceUrlVariable} is unset: the service's default bind. */
export const DefaultServiceUrl = "http://127.0.0.1:8000"

/**
 * Interface the dev server binds. Loopback only: the proxy forwards the service's bearer token,
 * so the dev server is never reachable from other machines.
 */
export const DevHost = "127.0.0.1"

/** Path prefix of every service API route; the dev server proxies it to the service. */
export const ApiPathPrefix = "/api"

/**
 * Request header the proxy removes. The service rejects requests whose `Origin` is not its own,
 * and a proxied request carries the dev server's origin.
 */
export const OriginHeader = "origin"

/** Largest TCP port. */
const MaxPort = 65_535

/** A decimal port number. */
const PortPattern = /^\d+$/

/**
 * Parse the dev server port.
 *
 * @param {string} text the variable's value.
 * @return {number} the port.
 * @throws {Error} when `text` is not an integer in 1..65535 (naming the variable and the value).
 */
export function parseDevPort(text) {
  const port = Number(text)
  if (!PortPattern.test(text) || port < 1 || port > MaxPort)
    throw new Error(`${DevPortVariable} must be a port number in 1..${MaxPort}, got "${text}"`)
  return port
}

/**
 * Strip the browser's `Origin` from a proxied request (http-proxy-middleware `on.proxyReq`).
 *
 * @param {import("node:http").ClientRequest} proxyRequest the outgoing request to the service.
 */
export function removeOriginHeader(proxyRequest) {
  proxyRequest.removeHeader(OriginHeader)
}

/**
 * Build the dev configuration.
 *
 * @param {object} [options]
 * @param {Record<string, string|undefined>} [options.env] the environment to read (default: `process.env`).
 * @return {import("webpack").Configuration} the configuration, with its `devServer` section.
 */
export function createDevWebpackConfig({ env = process.env } = {}) {
  const common = createCommonWebpackConfig({
      mode: "development",
      tsTransformers: [ReactRefreshTypeScript()]
    }),
    { [DevPortVariable]: portText = String(DefaultDevPort), [ServiceUrlVariable]: serviceUrl = DefaultServiceUrl } = env
  return {
    ...common,
    entry: EntrySubpath,
    devtool: "eval-cheap-module-source-map",
    output: { ...common.output, filename: "assets/[name].js" },
    plugins: [...common.plugins, new ReactRefreshPlugin()],
    devServer: {
      host: DevHost,
      port: parseDevPort(portText),
      hot: true,
      static: false,
      // Every client-side route under the basename gets the SPA page.
      historyApiFallback: { index: `${PublicPath}${IndexHtmlFile}` },
      proxy: [
        {
          context: [ApiPathPrefix],
          target: serviceUrl,
          changeOrigin: true,
          on: { proxyReq: removeOriginHeader }
        }
      ]
    }
  }
}

export default createDevWebpackConfig()
