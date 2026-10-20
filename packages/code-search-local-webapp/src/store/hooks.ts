import { useDispatch, useSelector } from "react-redux"

import type {
  CodeSearchDispatch,
  CodeSearchRootState
} from "./createCodeSearchStore.js"

/** Typed dispatch hook (never use the raw `useDispatch`). */
export const useCodeSearchDispatch = useDispatch.withTypes<CodeSearchDispatch>()

/** Typed selector hook (never use the raw `useSelector`). */
export const useCodeSearchSelector =
  useSelector.withTypes<CodeSearchRootState>()
