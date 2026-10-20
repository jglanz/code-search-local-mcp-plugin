export interface Shape {
  width: number
  height: number
}

export function width(shape: Pick<Shape, "width">): number {
  return shape.width
}
