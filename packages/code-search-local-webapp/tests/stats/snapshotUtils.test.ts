import { describe, expect, it } from "@jest/globals"

import { ApiFixtures } from "@code-search-local/code-search-local-api/testing"
import {
  countActiveJobs,
  findProjectById,
  isActiveJob,
  jobProgressOf,
  listProjectJobs,
  listProjects
} from "@code-search-local/code-search-local-webapp"

/** Half of the running job's changed files are processed. */
const RunningJobProgress = 0.5

describe("listProjects", () => {
  it("lists every project ordered by root", () => {
    expect(
      listProjects(ApiFixtures.Snapshot).map(({ project_path }) => project_path)
    ).toEqual([ApiFixtures.IdleProjectPath, ApiFixtures.ProjectPath])
  })

  it("is empty without projects", () => {
    expect(listProjects({ ...ApiFixtures.Snapshot, projects: {} })).toEqual([])
  })
})

describe("findProjectById", () => {
  it("finds a project by the digest of its root", () => {
    expect(findProjectById(ApiFixtures.Snapshot, ApiFixtures.ProjectId)).toBe(
      ApiFixtures.Project
    )
  })

  it("finds nothing for an unknown id", () => {
    expect(
      findProjectById(ApiFixtures.Snapshot, ApiFixtures.DaemonId)
    ).toBeUndefined()
  })
})

describe("listProjectJobs", () => {
  it("lists one project's jobs, most recently queued first", () => {
    expect(
      listProjectJobs(ApiFixtures.Snapshot, ApiFixtures.ProjectPath).map(
        ({ job_id }) => job_id
      )
    ).toEqual([ApiFixtures.RunningJobId, ApiFixtures.SucceededJobId])
  })

  it("lists nothing for a project without jobs", () => {
    expect(
      listProjectJobs(ApiFixtures.Snapshot, ApiFixtures.IdleProjectPath)
    ).toEqual([])
  })
})

describe("isActiveJob and countActiveJobs", () => {
  it("counts queued and running jobs", () => {
    expect(isActiveJob(ApiFixtures.RunningJob)).toBe(true)
    expect(countActiveJobs(ApiFixtures.Snapshot, ApiFixtures.ProjectPath)).toBe(
      1
    )
  })

  it("does not count terminal jobs", () => {
    expect(isActiveJob(ApiFixtures.SucceededJob)).toBe(false)
    expect(
      countActiveJobs(ApiFixtures.Snapshot, ApiFixtures.IdleProjectPath)
    ).toBe(0)
  })
})

describe("jobProgressOf", () => {
  it("is the processed share of the changed files", () => {
    expect(jobProgressOf(ApiFixtures.RunningJob)).toBe(RunningJobProgress)
    expect(jobProgressOf(ApiFixtures.SucceededJob)).toBe(1)
  })

  it("is unknown before the job counted its files", () => {
    expect(
      jobProgressOf({ ...ApiFixtures.RunningJob, files_total: undefined })
    ).toBeUndefined()
    expect(
      jobProgressOf({ ...ApiFixtures.RunningJob, files_total: 0 })
    ).toBeUndefined()
  })
})
