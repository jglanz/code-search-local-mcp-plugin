/**
 * @jest-environment jest-fixed-jsdom
 */
import { describe, expect, it } from "@jest/globals"
import { screen, within } from "@testing-library/react"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  JobsPanel,
  ViewState,
  ViewStateKind
} from "@code-search-local/code-search-local-webapp"

import { FakeFetch } from "../common/FakeFetch.js"
import { RenderWithStore } from "../common/RenderWithStore.js"

/** A failure reason of a sample job. */
const FailureReason = "Project directory is missing"

/** The running job's progress in percent. */
const RunningPercent = "50"

describe("JobsPanel", () => {
  it("shows each job's status and progress over its changed files", () => {
    RenderWithStore.render(
      <JobsPanel jobs={[ApiFixtures.RunningJob, ApiFixtures.SucceededJob]} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    const running = screen.getByTestId(
      JobsPanel.rowTestIdOf(ApiFixtures.RunningJobId)
    )
    expect(running).toHaveTextContent(ApiFixtures.RunningJob.status)
    expect(running).toHaveTextContent(`2 / 4 ${JobsPanel.FilesUnit}`)
    expect(within(running).getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      RunningPercent
    )
    expect(
      screen.getByTestId(JobsPanel.rowTestIdOf(ApiFixtures.SucceededJobId))
    ).toHaveTextContent("7.9 s")
  })

  it("shows a failed job's reason, and an empty state without jobs", () => {
    const failed = {
        ...ApiFixtures.SucceededJob,
        status: "failed" as const,
        files_total: undefined,
        result: undefined,
        error: FailureReason
      },
      { unmount } = RenderWithStore.render(
        <JobsPanel jobs={[failed]} />,
        RenderWithStore.newServices(FakeFetch.create({}).fetch)
      ),
      row = screen.getByTestId(JobsPanel.rowTestIdOf(failed.job_id))
    expect(row).toHaveTextContent(FailureReason)
    expect(within(row).queryByRole("progressbar")).not.toBeInTheDocument()
    unmount()
    RenderWithStore.render(
      <JobsPanel jobs={[]} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(
      screen.getByTestId(
        ViewState.testIdOf(JobsPanel.TestId, ViewStateKind.empty)
      )
    ).toHaveTextContent(JobsPanel.EmptyMessage)
  })

  it("lists at most the most recent jobs", () => {
    const jobs = Array.from({ length: JobsPanel.MaxJobs + 2 }, (_, index) => ({
      ...ApiFixtures.SucceededJob,
      job_id: `job-${index}`
    }))
    RenderWithStore.render(
      <JobsPanel jobs={jobs} />,
      RenderWithStore.newServices(FakeFetch.create({}).fetch)
    )
    expect(
      screen.queryByTestId(JobsPanel.rowTestIdOf(`job-${JobsPanel.MaxJobs}`))
    ).not.toBeInTheDocument()
    expect(
      screen.getByTestId(JobsPanel.rowTestIdOf("job-0"))
    ).toBeInTheDocument()
  })
})
