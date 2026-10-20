import { combineReducers, configureStore } from "@reduxjs/toolkit"

import { CodeSearchApi } from "../api/CodeSearchApi.js"
import type { CodeSearchServices } from "../services/CodeSearchServices.js"
import { AuthSlice, createAuthInitialState } from "./auth/AuthSlice.js"
import { SliceName } from "./SliceName.js"

/** The root reducer (every slice keyed by its {@link SliceName}). */
export const codeSearchRootReducer = combineReducers({
  [CodeSearchApi.reducerPath]: CodeSearchApi.reducer,
  [SliceName.auth]: AuthSlice.reducer
})

/** The root state. */
export type CodeSearchRootState = ReturnType<typeof codeSearchRootReducer>

/**
 * Create the app store. `services` becomes the thunk `extraArgument` (and RTK Query's
 * `api.extra`), so tests inject a fake fetch and origin. The auth slice starts from the token
 * the services' token store holds (a preloaded auth state wins).
 *
 * @param services the environment thunks and queries run against.
 * @param preloadedState optional initial state.
 * @returns the store.
 */
export function createCodeSearchStore(
  services: CodeSearchServices,
  preloadedState?: Partial<CodeSearchRootState>
) {
  return configureStore({
    reducer: codeSearchRootReducer,
    preloadedState: {
      [SliceName.auth]: createAuthInitialState(services.tokenStore.read()),
      ...preloadedState
    },
    middleware: getDefaultMiddleware =>
      getDefaultMiddleware({ thunk: { extraArgument: services } }).concat(
        CodeSearchApi.middleware
      )
  })
}

/** The store type. */
export type CodeSearchStore = ReturnType<typeof createCodeSearchStore>

/** The store's dispatch. */
export type CodeSearchDispatch = CodeSearchStore["dispatch"]
