import { selectToken } from "../store/auth/AuthSlice.js"
import { useCodeSearchSelector } from "../store/hooks.js"
import { ConnectScreen } from "./ConnectScreen.js"

/** Props of {@link AuthGate}. */
export interface AuthGateProps {
  /** What to render once a token is known. */
  children: React.ReactNode
}

/**
 * Renders the page only while a bearer token is known; otherwise (never connected, or the
 * service rejected the token) the connect screen.
 *
 * @param props the gate props.
 * @returns the page or the connect screen.
 */
export function AuthGate({ children }: AuthGateProps): React.ReactElement {
  const token = useCodeSearchSelector(selectToken)
  return token == null ? <ConnectScreen /> : <>{children}</>
}
