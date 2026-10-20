import CheckCircle from "@mui/icons-material/CheckCircle"
import CloudOff from "@mui/icons-material/CloudOff"
import Box from "@mui/material/Box"
import Chip from "@mui/material/Chip"
import Stack from "@mui/material/Stack"
import Typography from "@mui/material/Typography"

import type {
  ModelInfo,
  StatsSnapshot
} from "@code-search-local/code-search-local-api"

import { formatScore, formatTime, NoValue } from "../stats/formatUtils.js"

/** One labelled fact of the header. */
export interface ServiceFact {
  /** The fact's label. */
  label: string

  /** Its formatted value. */
  value: string

  /** Test id of the value. */
  testId: string
}

/** Props of {@link ServiceHeader}. */
export interface ServiceHeaderProps {
  /** The latest statistics snapshot. */
  snapshot: StatsSnapshot

  /** The service answered the latest health check and stats request. */
  online: boolean

  /** When the snapshot was last refreshed, in ms since the epoch. */
  refreshedAt: number
}

/**
 * The service's status above every dashboard page: online or offline, the daemon, the shared
 * model (name, backend, device, whether it is resident), the relevance threshold and when the
 * figures were last refreshed.
 *
 * @param props the header props.
 * @returns the header.
 */
export function ServiceHeader({
  snapshot,
  online,
  refreshedAt
}: ServiceHeaderProps): React.ReactElement {
  return (
    <Box
      component="section"
      aria-label={ServiceHeader.Label}
      data-testid={ServiceHeader.TestId}
      sx={{ p: 2, border: 1, borderColor: "divider", borderRadius: 1 }}
    >
      <Stack
        direction="row"
        spacing={1.5}
        sx={{ alignItems: "center", mb: 1.5 }}
      >
        <Typography variant="h6" component="h2">
          {ServiceHeader.Label}
        </Typography>
        <Chip
          size="small"
          data-testid={ServiceHeader.StatusTestId}
          color={online ? "success" : "error"}
          icon={online ? <CheckCircle /> : <CloudOff />}
          label={
            online ? ServiceHeader.OnlineLabel : ServiceHeader.OfflineLabel
          }
        />
      </Stack>
      <Box
        component="dl"
        sx={{
          m: 0,
          display: "grid",
          gap: 1.5,
          gridTemplateColumns: `repeat(auto-fit, minmax(${ServiceHeader.MinFactWidthPx}px, 1fr))`
        }}
      >
        {ServiceHeader.listFacts(snapshot, refreshedAt).map(
          ({ label, value, testId }) => (
            <Box key={testId}>
              <Typography
                component="dt"
                variant="caption"
                color="text.secondary"
              >
                {label}
              </Typography>
              <Typography
                component="dd"
                variant="body2"
                data-testid={testId}
                sx={{ m: 0, overflowWrap: "anywhere" }}
              >
                {value}
              </Typography>
            </Box>
          )
        )}
      </Box>
    </Box>
  )
}

/** Companion constants and helpers for {@link ServiceHeader}. */
export namespace ServiceHeader {
  /** The header's heading and accessible name. */
  export const Label = "Service"

  /** Test id of the header. */
  export const TestId = "service-header"

  /** Test id of the online/offline chip. */
  export const StatusTestId = "service-status"

  /** Chip text while the service answers. */
  export const OnlineLabel = "Online"

  /** Chip text when the service does not answer or the snapshot was read from disk. */
  export const OfflineLabel = "Offline"

  /** Value of the resident fact when the model is loaded. */
  export const ResidentLabel = "Loaded"

  /** Value of the resident fact when the model is not loaded. */
  export const NotResidentLabel = "Not loaded"

  /** Narrowest fact column in px. */
  export const MinFactWidthPx = 160

  /**
   * The header's facts, in display order.
   *
   * @param snapshot the statistics snapshot.
   * @param refreshedAt when it was refreshed (ms since the epoch).
   * @returns the facts.
   */
  export function listFacts(
    snapshot: StatsSnapshot,
    refreshedAt: number
  ): ServiceFact[] {
    const {
        daemon_id: daemonId,
        shared: {
          model = {} as ModelInfo,
          model_resident: resident,
          search_hit_min_score: threshold
        }
      } = snapshot,
      { model: modelId = NoValue, backend = NoValue, device = NoValue } = model
    return [
      { label: "Daemon", value: daemonId, testId: "service-daemon" },
      { label: "Model", value: modelId, testId: "service-model" },
      { label: "Backend", value: backend, testId: "service-backend" },
      { label: "Device", value: device, testId: "service-device" },
      {
        label: "Model resident",
        value: resident ? ResidentLabel : NotResidentLabel,
        testId: "service-resident"
      },
      {
        label: "Relevance threshold",
        value: formatScore(threshold),
        testId: "service-threshold"
      },
      {
        label: "Last refresh",
        value: formatTime(refreshedAt),
        testId: "service-refreshed"
      }
    ]
  }
}
