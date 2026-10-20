import type {
  HealthResponse,
  Job,
  ModelInfo,
  PathsResponse,
  PathStat,
  ProjectStats,
  SearchTotals,
  SharedStats,
  StatsSnapshot
} from "../generated/index.js"

/**
 * Realistic API bodies for tests of this package and of its clients, shaped like the service's
 * responses (timestamps carry the `+00:00` offset Python's `isoformat()` writes). Exported from
 * the `testing` subpath only, never from the package's main entry. Changing a value changes what
 * every client test renders and asserts.
 */
export namespace ApiFixtures {
  /** The daemon that wrote the snapshots (32 hex characters). */
  export const DaemonId = "5f0c9a1e7b2d4c6a8e0f1a2b3c4d5e6f"

  /** The registered project's canonical root. */
  export const ProjectPath = "/home/dev/projects/sample-app"

  /** SHA-256 hex digest of {@link ProjectPath}, as the service computes `project_id`. */
  export const ProjectId =
    "8c5be1f4b1a76c2e0d3f9e8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c"

  /** A second project that has never been indexed or searched. */
  export const IdleProjectPath = "/home/dev/projects/empty-notes"

  /** SHA-256 hex digest of {@link IdleProjectPath}. */
  export const IdleProjectId =
    "1d2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c"

  /** The committed generation of {@link ProjectPath}. */
  export const Generation = "gen-0a1b2c3d4e5f60718293a4b5c6d7e8f9"

  /** Merkle root of the files {@link Generation} indexed. */
  export const MerkleRoot =
    "c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00c0ffee00"

  /** The relevance threshold in effect. */
  export const SearchHitMinScore = 0.5

  /** When the daemon started. */
  export const StartedAt = "2026-10-19T13:58:02.104233+00:00"

  /** When the project was registered. */
  export const RegisteredAt = "2026-10-19T14:00:00.512301+00:00"

  /** When the committed generation was built. */
  export const IndexedAt = "2026-10-19T14:01:47.990012+00:00"

  /** When the most recent search ran. */
  export const LastSearchAt = "2026-10-19T14:05:12.345678+00:00"

  /** The running job of {@link ProjectPath}. */
  export const RunningJobId = "9a8b7c6d5e4f30211203f4e5d6c7b8a9"

  /** The succeeded job of {@link ProjectPath}. */
  export const SucceededJobId = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"

  /** The shared embedding model. */
  export const Model: ModelInfo = {
    model: "google/embeddinggemma-300m",
    revision: "57c266a740f537b4dc058e1b0cda161fd15afa75",
    requested_revision: "main",
    requested_backend: "auto",
    backend: "cpu",
    device: "cpu",
    gpu: null,
    fallback_reason: null,
    dimension: 768,
    encoding: { normalize: true, max_chars: 8_000, format_version: 1 }
  }

  /** A path returned by searches, with hits and misses. */
  export const MainPath: PathStat = {
    path: "src/app/main.py",
    chunks: 4,
    appearances: 3,
    hits: 2,
    misses: 1,
    hit_ratio: 0.6667,
    top_ranked: 1,
    chunk_appearances: 5,
    best_score: 0.71,
    last_seen_at: LastSearchAt
  }

  /** A path returned once, below the threshold. */
  export const UtilPath: PathStat = {
    path: "src/app/util/strings.py",
    chunks: 2,
    appearances: 1,
    hits: 0,
    misses: 1,
    hit_ratio: 0,
    top_ranked: 0,
    chunk_appearances: 1,
    best_score: 0.42,
    last_seen_at: LastSearchAt
  }

  /** A path never returned by a search (zero counters, null score and time). */
  export const ReadmePath: PathStat = {
    path: "README.md",
    chunks: 3,
    appearances: 0,
    hits: 0,
    misses: 0,
    hit_ratio: 0,
    top_ranked: 0,
    chunk_appearances: 0,
    best_score: null,
    last_seen_at: null
  }

  /** {@link ProjectPath} after an index and three searches, with every analytics field. */
  export const Project: ProjectStats = {
    project_path: ProjectPath,
    project_id: ProjectId,
    registered_at: RegisteredAt,
    files: 3,
    chunks: 9,
    generation: Generation,
    file_patterns: null,
    watch_enabled: true,
    files_scanned: 5,
    files_supported: 3,
    files_skipped: 0,
    source_bytes: 18_432,
    indexed_at: IndexedAt,
    changes: { added: 3, modified: 0, deleted: 0 },
    reused_chunks: 0,
    model: Model,
    active_model: Model,
    merkle_root: MerkleRoot,
    index_bytes: 65_536,
    index_failures: 0,
    updates_detected: 3,
    cache_hits: 6,
    cache_misses: 12,
    cache_hit_ratio: 0.3333,
    query_cache_hits: 1,
    query_cache_misses: 2,
    query_cache_hit_ratio: 0.3333,
    searches: 3,
    search_failures: 0,
    search_relevance_hits: 2,
    search_relevance_misses: 1,
    search_relevance_hit_ratio: 0.6667,
    search_result_hits: 3,
    search_result_misses: 0,
    search_result_hit_ratio: 1,
    search_zero_results: 0,
    search_seconds: 0.084,
    last_search_seconds: 0.021,
    last_search_at: LastSearchAt,
    last_search_top_score: 0.71,
    top_paths: [MainPath, UtilPath]
  }

  /** A registered project that has never been indexed or searched (optional keys absent). */
  export const IdleProject: ProjectStats = {
    project_path: IdleProjectPath,
    project_id: IdleProjectId,
    registered_at: RegisteredAt,
    files: 0,
    chunks: 0,
    generation: null,
    index_failures: 0,
    updates_detected: 0,
    cache_hits: 0,
    cache_misses: 0,
    cache_hit_ratio: 0,
    query_cache_hit_ratio: 0,
    searches: 0,
    search_failures: 0,
    search_relevance_hit_ratio: 0,
    search_result_hit_ratio: 0,
    top_paths: []
  }

  /** A job of {@link ProjectPath} halfway through its changed files. */
  export const RunningJob: Job = {
    job_id: RunningJobId,
    project_path: ProjectPath,
    status: "running",
    queued_at: "2026-10-19T14:06:00.000101+00:00",
    started_at: "2026-10-19T14:06:00.250333+00:00",
    files_processed: 2,
    files_total: 4,
    incremental: true,
    file_patterns: null,
    error: null
  }

  /** The job that committed {@link Generation}. */
  export const SucceededJob: Job = {
    job_id: SucceededJobId,
    project_path: ProjectPath,
    status: "succeeded",
    queued_at: "2026-10-19T14:01:40.000001+00:00",
    started_at: "2026-10-19T14:01:40.100002+00:00",
    finished_at: IndexedAt,
    duration_seconds: 7.89,
    files_processed: 3,
    files_total: 3,
    incremental: true,
    file_patterns: null,
    error: null,
    result: {
      files: 3,
      files_scanned: 5,
      files_supported: 3,
      files_skipped: 0,
      chunks: 9,
      source_bytes: 18_432,
      indexed_at: IndexedAt,
      changes: { added: 3, modified: 0, deleted: 0 },
      reused_chunks: 0,
      model: Model,
      merkle_root: MerkleRoot,
      needs_rebuild: false,
      generation: Generation,
      index_bytes: 65_536
    }
  }

  /** Shared model and service counters, with the threshold in effect. */
  export const Shared: SharedStats = {
    model_resident: true,
    model: Model,
    gpu_memory_bytes: 0,
    max_concurrent_inference: 1,
    model_loads: 1,
    inference_batches: 4,
    inference_seconds: 1.25,
    embedded_texts: 12,
    search_hit_min_score: SearchHitMinScore
  }

  /** Totals over {@link Project} and {@link IdleProject}. */
  export const Totals: SearchTotals = {
    projects: 2,
    files: 3,
    chunks: 9,
    searches: 3,
    search_failures: 0,
    search_zero_results: 0,
    search_relevance_hits: 2,
    search_relevance_misses: 1,
    search_relevance_hit_ratio: 0.6667,
    search_result_hits: 3,
    search_result_misses: 0,
    search_result_hit_ratio: 1,
    query_cache_hits: 1,
    query_cache_misses: 2,
    query_cache_hit_ratio: 0.3333,
    cache_hits: 6,
    cache_misses: 12,
    cache_hit_ratio: 0.3333
  }

  /** The full snapshot `GET /api/v1/stats` answers. */
  export const Snapshot: StatsSnapshot = {
    schema_version: 2,
    daemon_id: DaemonId,
    sequence: 42,
    started_at: StartedAt,
    online: true,
    projects: { [ProjectPath]: Project, [IdleProjectPath]: IdleProject },
    jobs: { [RunningJobId]: RunningJob, [SucceededJobId]: SucceededJob },
    shared: Shared,
    totals: Totals
  }

  /** `GET /api/v1/paths` of {@link ProjectPath}: every file, sorted by path. */
  export const Paths: PathsResponse = {
    project_path: ProjectPath,
    project_id: ProjectId,
    generation: Generation,
    search_hit_min_score: SearchHitMinScore,
    paths: [ReadmePath, MainPath, UtilPath]
  }

  /** `GET /api/v1/paths` of a project without a committed generation. */
  export const NoGenerationPaths: PathsResponse = {
    project_path: IdleProjectPath,
    project_id: IdleProjectId,
    generation: null,
    search_hit_min_score: SearchHitMinScore,
    paths: []
  }

  /** `GET /api/v1/health`. */
  export const Health: HealthResponse = { status: "ok", daemon_id: DaemonId }
}
