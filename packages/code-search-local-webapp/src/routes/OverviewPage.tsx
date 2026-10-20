import Stack from "@mui/material/Stack"
import Typography from "@mui/material/Typography"
import { useEffect } from "react"

import { AppTitle } from "../app/AppTitle.js"
import { HitMissPanel } from "../dashboard/HitMissPanel.js"
import { ProjectsTable } from "../dashboard/ProjectsTable.js"
import { StatsView } from "../dashboard/StatsView.js"
import { TotalsCards } from "../dashboard/TotalsCards.js"

/**
 * The service overview, the landing page under the basename: the service header, the totals,
 * the three hit/miss measures over every project and the projects table.
 *
 * @returns the page.
 */
export function OverviewPage(): React.ReactElement {
  useEffect(() => {
    document.title = AppTitle.of(OverviewPage.Title)
  }, [])
  return (
    <Stack spacing={3} data-testid={OverviewPage.TestId}>
      <Typography variant="h5" component="h1">
        {OverviewPage.Title}
      </Typography>
      <StatsView>
        {snapshot => (
          <>
            <TotalsCards totals={snapshot.totals} />
            <HitMissPanel
              title={OverviewPage.HitMissTitle}
              scope={OverviewPage.HitMissScope}
              source={snapshot.totals}
              threshold={snapshot.shared.search_hit_min_score}
            />
            <ProjectsTable snapshot={snapshot} />
          </>
        )}
      </StatsView>
    </Stack>
  )
}

/** Companion constants for {@link OverviewPage}. */
export namespace OverviewPage {
  /** The page heading (and its document title). */
  export const Title = "Overview"

  /** Heading of the hit/miss measures over every project. */
  export const HitMissTitle = "Search quality, all projects"

  /** Test id scope of the totals' hit/miss meters. */
  export const HitMissScope = "totals"

  /** Test id of the page root. */
  export const TestId = "overview-page"
}
