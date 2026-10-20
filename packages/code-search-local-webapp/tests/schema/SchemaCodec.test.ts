import { describe, expect, it } from "@jest/globals"
import { z } from "zod"

import {
  NestedError,
  SchemaCodec
} from "@code-search-local/code-search-local-webapp"

const PointSchema = z.strictObject({ x: z.number(), y: z.number() })

/** A 2-D point. */
type Point = z.infer<typeof PointSchema>

const PointCodec = SchemaCodec.create("Point", PointSchema)

describe("SchemaCodec.decode", () => {
  it("returns Right for a valid value", () => {
    expect(PointCodec.decode({ x: 1, y: 2 }).getOrThrow()).toEqual({
      x: 1,
      y: 2
    })
  })

  it("returns Left(NestedError) naming the codec and the issue path", () => {
    const error = PointCodec.decode({ x: "1", y: 2 }).getLeftOrThrow()
    expect(error).toBeInstanceOf(NestedError)
    expect(error.message).toContain("Point: decode failed: x:")
    expect(error.context).toEqual({
      codec: "Point",
      direction: SchemaCodec.Direction.decode
    })
  })
})

describe("SchemaCodec.decodeJson", () => {
  it("parses and validates JSON text", () => {
    expect(PointCodec.decodeJson('{"x":3,"y":4}').getOrThrow()).toEqual({
      x: 3,
      y: 4
    })
  })

  it("returns Left(decode failed) for valid JSON with the wrong shape", () => {
    const error = PointCodec.decodeJson('{"x":"1","y":2}').getLeftOrThrow()
    expect(error.message).toContain("Point: decode failed")
    expect(error.context).toMatchObject({
      direction: SchemaCodec.Direction.decode
    })
  })

  it("returns Left for malformed JSON with the parse error as cause", () => {
    const error = PointCodec.decodeJson("{not json").getLeftOrThrow()
    expect(error.message).toBe("Point: invalid JSON")
    expect(error.cause).toBeInstanceOf(SyntaxError)
  })
})

describe("SchemaCodec.encode", () => {
  it("returns Right for a valid value", () => {
    expect(PointCodec.encode({ x: 2, y: 3 }).getOrThrow()).toEqual({
      x: 2,
      y: 3
    })
  })

  it("returns Left(encode failed) for an invalid value", () => {
    const error = PointCodec.encode({
      x: 1
    } as unknown as Point).getLeftOrThrow()
    expect(error.context).toMatchObject({
      direction: SchemaCodec.Direction.encode
    })
  })
})

describe("SchemaCodec.assertEncode", () => {
  it("returns a valid value", () => {
    expect(PointCodec.assertEncode({ x: 0, y: 1 })).toEqual({ x: 0, y: 1 })
  })

  it("throws the NestedError for an invalid value", () => {
    expect(() => PointCodec.assertEncode({ y: 1 } as unknown as Point)).toThrow(
      "Point: encode failed"
    )
  })
})

describe("SchemaCodec.encodeJson", () => {
  it("serialises a valid value", () => {
    expect(PointCodec.encodeJson({ x: 1, y: 1 }, 0).getOrThrow()).toBe(
      '{"x":1,"y":1}'
    )
  })

  it("refuses an invalid value before it is persisted", () => {
    const invalid = { x: 1, y: 1, z: 1 } as unknown as Point
    expect(PointCodec.encode(invalid).isLeft()).toBe(true)
    expect(PointCodec.encodeJson(invalid).getLeftOrThrow().message).toContain(
      "Point: encode failed"
    )
  })
})

describe("SchemaCodec.assertDecode", () => {
  it("returns the validated value", () => {
    expect(PointCodec.assertDecode({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 })
  })

  it("throws the NestedError for an invalid value", () => {
    expect(() => PointCodec.assertDecode({})).toThrow(NestedError)
  })
})

describe("SchemaCodec.describeIssue", () => {
  it("prefixes the issue path", () => {
    expect(
      SchemaCodec.describeIssue({
        code: "custom",
        path: ["a", 0],
        message: "bad",
        input: null
      })
    ).toBe("a.0: bad")
  })

  it("omits an empty path", () => {
    expect(
      SchemaCodec.describeIssue({
        code: "custom",
        path: [],
        message: "bad",
        input: null
      })
    ).toBe("bad")
  })
})
