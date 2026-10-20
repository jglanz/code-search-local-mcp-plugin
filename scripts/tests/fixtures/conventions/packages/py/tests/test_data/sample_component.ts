// Sample source a Python test indexes: no tsconfig.json at the package root, so never checked.
import { local } from "./local.js"
import { z } from "zod"
export function Undocumented() { return [local, z] }
