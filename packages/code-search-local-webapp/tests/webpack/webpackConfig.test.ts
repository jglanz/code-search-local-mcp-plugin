import path from "node:path"

import { describe, expect, it, jest } from "@jest/globals"

import {
  IndexHtmlFile,
  OutputPath,
  PackagePath,
  PublicPath,
  createCommonWebpackConfig
} from "../../etc/webpack/webpack.common.mjs"
import {
  ApiPathPrefix,
  DefaultDevPort,
  DefaultServiceUrl,
  DevPortVariable,
  OriginHeader,
  ServiceUrlVariable,
  createDevWebpackConfig,
  parseDevPort,
  removeOriginHeader
} from "../../etc/webpack/webpack.dev.mjs"
import { createProdWebpackConfig } from "../../etc/webpack/webpack.prod.mjs"

/** A dev port other than the default. */
const CustomPort = "9123"

/** A service URL other than the default. */
const CustomServiceUrl = "http://127.0.0.1:9000"

/** Values that are not ports. */
const InvalidPorts = ["0", "65536", "80a", "", "-1"]

/** Webpack's production mode. */
const ProductionMode = "production"

/** Prod output file name: content-hashed under `assets/`. */
const HashedFilename = "assets/[name].[contenthash].js"

describe("createCommonWebpackConfig", () => {
  it("emits into this package's dist/ under the /ui/ public path", () => {
    const config = createCommonWebpackConfig({ mode: ProductionMode })
    expect(config.output).toMatchObject({
      path: OutputPath,
      publicPath: PublicPath,
      clean: true
    })
    expect(OutputPath).toBe(path.join(PackagePath, "dist"))
  })

  it("adds no ts-loader transformers unless asked", () => {
    const [, tsRule] = createCommonWebpackConfig({ mode: ProductionMode })
      .module.rules
    expect(tsRule.use.options.getCustomTransformers()).toEqual({ before: [] })
  })
})

describe("createProdWebpackConfig", () => {
  it("content-hashes every script under the public path", () => {
    const config = createProdWebpackConfig()
    expect(config.mode).toBe(ProductionMode)
    expect(config.output).toMatchObject({
      filename: HashedFilename,
      publicPath: PublicPath
    })
  })

  it("has no dev server", () => {
    expect(createProdWebpackConfig().devServer).toBeUndefined()
  })
})

describe("createDevWebpackConfig", () => {
  it("defaults to the documented port and proxies /api to the default service", () => {
    const { devServer } = createDevWebpackConfig({ env: {} }),
      [proxy] = devServer.proxy
    expect(devServer.port).toBe(DefaultDevPort)
    expect(devServer.hot).toBe(true)
    expect(devServer.historyApiFallback).toEqual({
      index: `${PublicPath}${IndexHtmlFile}`
    })
    expect(proxy).toMatchObject({
      context: [ApiPathPrefix],
      target: DefaultServiceUrl,
      changeOrigin: true
    })
  })

  it("reads the port and the service URL from the environment", () => {
    const { devServer } = createDevWebpackConfig({
      env: {
        [DevPortVariable]: CustomPort,
        [ServiceUrlVariable]: CustomServiceUrl
      }
    })
    expect(devServer.port).toBe(Number(CustomPort))
    expect(devServer.proxy[0].target).toBe(CustomServiceUrl)
  })

  it("fails on a port variable that is not a port", () => {
    expect(() =>
      createDevWebpackConfig({ env: { [DevPortVariable]: InvalidPorts[0] } })
    ).toThrow(DevPortVariable)
  })
})

describe("parseDevPort", () => {
  it("parses a decimal port", () => {
    expect(parseDevPort(CustomPort)).toBe(Number(CustomPort))
  })

  it.each(InvalidPorts)("rejects %j, naming the variable", text => {
    expect(() => parseDevPort(text)).toThrow(DevPortVariable)
  })
})

describe("removeOriginHeader", () => {
  it("removes the Origin header from the proxied request", () => {
    const removeHeader = jest.fn()
    removeOriginHeader({ removeHeader })
    expect(removeHeader).toHaveBeenCalledWith(OriginHeader)
  })

  it("propagates a failure of the outgoing request", () => {
    const failure = new Error("headers already sent")
    expect(() =>
      removeOriginHeader({
        removeHeader: () => {
          throw failure
        }
      })
    ).toThrow(failure)
  })
})
