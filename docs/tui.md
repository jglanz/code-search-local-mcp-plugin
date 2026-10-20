# Statistics terminal UI

`code-search-local stats` shows the service's statistics snapshot in the
terminal. The report, the live view, `stats --json`, `GET /api/v1/stats`, the
`get_index_stats` MCP tool and the `code-search-local://stats` resources all
read the same snapshot; the terminal UI only renders it. From a source checkout,
run the same commands through `hatch run cpu:cli stats …` (or your backend
prefix).

- [Modes](#modes)
- [Sections and columns](#sections-and-columns)
- [Live view](#live-view)
- [Search hit and miss statistics](#search-hit-and-miss-statistics)
- [Per-path statistics](#per-path-statistics)
- [Troubleshooting](#troubleshooting)

## Modes

```sh
# Inline report: printed once into terminal scrollback, including the details table.
code-search-local stats

# The same report as plain text, when stdout is a file or a pipe.
code-search-local stats > stats.txt
code-search-local stats | less

# Fullscreen live view that follows the service's change notifications (needs a terminal).
code-search-local stats --live

# The snapshot as JSON on stdout, for scripts, pipes and files.
code-search-local stats --json

# Any mode, limited to one project root.
code-search-local stats --project ./my-project
code-search-local stats --project /absolute/path/to/project --live
code-search-local stats --project ./my-project --json > project-stats.json
```

| Option           | Effect                                                                                                                                                                                                                                                                                                                                                                                                   |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| (none)           | With a terminal on stdout, an inline Textual report of every section, written into the terminal scrollback. Otherwise, the same sections as [plain text](#plain-text-output). The command exits immediately either way.                                                                                                                                                                                  |
| `--live`         | Fullscreen Textual app with a header, a footer of key bindings, and updates delivered through local pub-sub IPC. It requires a terminal on stdout; redirected or piped, it is a usage error (exit status 2).                                                                                                                                                                                             |
| `--json`         | Writes the snapshot as indented JSON with sorted keys to stdout. It cannot be combined with `--live`; doing so is a usage error.                                                                                                                                                                                                                                                                         |
| `--project PATH` | Accepts a relative or absolute root and resolves it, including symlinks, to the canonical root. It limits the projects, top paths and jobs to that root. The summary totals (`totals`) and the shared model section still cover the whole service. An unregistered root fails with `Project is not registered: <root>`; a subdirectory of an indexed root is a different, usually unregistered, project. |

The CLI resolves its endpoint, token and storage from the same configuration as
every other command (see the
[configuration reference](../README.md#configuration-reference)). When the HTTP
request cannot connect, it reads the persisted database instead and labels the
result as an [offline snapshot](#offline-snapshots). Without a service token in
the storage directory, the command fails with
`Service is not configured; run code-search-local setup`.

### Plain-text output

When stdout is not a terminal, for example redirected to a file or piped into
`less`, `grep` or `cat`, `stats` does not start Textual. It prints the same five
sections as the inline report as plain text: box-drawing characters, but no
colour, style or cursor control sequences. A progress bar shows only its filled
part. The width is the value of `COLUMNS` when that variable is set, and 160
columns otherwise; cells wider than their column wrap within it.

The plain text is meant for people. Use `--json` whenever another program parses
the output.

## Sections and columns

The inline report, the plain-text report and the live view show five sections,
top to bottom. A value that is not known yet, for example a rate before any
search or the model before it has loaded, appears as `—`. The summary, the
projects table and the header show local time; the details table shows the
stored ISO 8601 UTC timestamps.

### Summary

The left column describes the service; the right column summarises all
registered projects, from the snapshot's `totals`.

| Field                      | Source and meaning                                                                                                                 |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Connection                 | `online` (green) for a snapshot from the running service, `offline snapshot` (red) for the persisted database or a lost connection |
| Daemon                     | `daemon_id` of the service process that wrote the snapshot; it changes on every restart                                            |
| Started                    | `started_at` of that service process                                                                                               |
| Model                      | `shared.model.model @ shared.model.revision`                                                                                       |
| Backend / device           | `shared.model.backend / shared.model.device`                                                                                       |
| Model resident             | `shared.model_resident`: whether the service currently holds the model in memory                                                   |
| Search hit threshold       | `shared.search_hit_min_score`, the relevance threshold the service started with                                                    |
| Projects, Files, Chunks    | Registered projects and the files and chunks of their committed indexes                                                            |
| Searches, Search failures  | All searches, and those that failed                                                                                                |
| Relevance hit rate         | [Relevance](#search-hit-and-miss-statistics) rate as `percentage (hits/misses)`                                                    |
| Non-empty results hit rate | [Non-empty result](#search-hit-and-miss-statistics) rate as `percentage (hits/misses)`                                             |
| Query cache hit rate       | [Query embedding cache](#search-hit-and-miss-statistics) rate as `percentage (hits/misses)`                                        |

### Projects

One row per project in the snapshot, titled
`Projects — hit rate % (hits/misses)`. Without registered projects, the table
shows `No projects registered`.

| Column                                    | Meaning                                                           |
| ----------------------------------------- | ----------------------------------------------------------------- |
| Project                                   | Canonical project root                                            |
| Files, Chunks                             | Files and chunks of the committed index                           |
| Last indexed                              | `indexed_at` of the committed index                               |
| Searches                                  | Searches of this project                                          |
| Relevance, Non-empty results, Query cache | The project's three hit rates, each as `percentage (hits/misses)` |
| Active jobs                               | The project's index jobs that are `queued` or `running`           |

### Top paths

The files that this project's searches returned most often: up to ten per
project, ordered by appearances and then by path. Each project's rows form one
group; the first row names the project. Without any recorded result, the table
shows `No search results recorded`. See
[per-path statistics](#per-path-statistics) for the exact meaning of each value.

| Column      | Meaning                                                             |
| ----------- | ------------------------------------------------------------------- |
| Project     | Canonical project root, on the first row of its group               |
| Path        | Project-relative file path                                          |
| Appearances | Searches whose results included the file                            |
| Hits        | Of those, searches in which one of its chunks reached the threshold |
| Misses      | `Appearances − Hits`                                                |
| Hit ratio   | `Hits / Appearances` as a percentage                                |
| Top-ranked  | Searches in which the file held the first result                    |
| Best score  | Highest score any of its chunks received, to three decimals         |

`chunk_appearances` and `last_seen_at` are in the JSON output and the details
table.

### Index jobs

The 20 most recently queued jobs, newest first. When the snapshot holds more,
the caption reads `Newest 20 of N jobs; details list every job`. Without jobs,
the table shows `No index jobs`.

| Column   | Meaning                                                                                                 |
| -------- | ------------------------------------------------------------------------------------------------------- |
| Job      | First eight characters of the job ID; `stats --json` and the details table show the full ID             |
| Project  | Canonical project root                                                                                  |
| Status   | `queued` or `running` (yellow), `succeeded` (green), `failed` (red), `cancelled` or `interrupted` (dim) |
| Files    | `files_processed / files_total`                                                                         |
| Progress | A bar and percentage of processed files; `—` until the job knows its file count                         |
| Duration | `duration_seconds`, to one decimal                                                                      |
| Error    | The job's error, shortened to 60 characters; the details table holds the complete message               |

### Details

A `Scope / Statistic / Value` table of every value in the snapshot, titled
`Code Search Local — online` or `Code Search Local — offline snapshot`. Scopes
are `Service` (top-level values, including every `totals.*` counter and ratio),
`Shared model`, one scope per project root, and `Job <job ID>` for every job.
Nested values use dotted names such as `model.backend`; lists such as
`top_paths` and `file_patterns` appear as JSON.

## Live view

### Key bindings

| Key      | Action                                                                                                       |
| -------- | ------------------------------------------------------------------------------------------------------------ |
| `q`      | Quit                                                                                                         |
| `Escape` | Quit (not listed in the footer)                                                                              |
| `r`      | Fetch a new snapshot immediately, through the same path as the initial one (HTTP, then the offline database) |
| `d`      | Hide or show the details table; the other sections stay visible                                              |

### Header and connection state

The header shows `Code Search Local` and a subtitle such as
`online · updated 14:03:07`: the connection state of the displayed snapshot and
the local time at which the view last displayed one. The subtitle reads
`offline snapshot · …` when the view shows persisted or stale data. Failed
refreshes appear as error notifications for ten seconds.

### Recovery after errors

If following the service fails, for example because the persisted database
cannot be read or the IPC socket reports an error, the view shows the error as a
notification, marks the displayed snapshot offline (also in the subtitle) and
subscribes again after a delay. Every failed attempt shows one notification. The
delay starts at one second, doubles after each further failure and is capped at
fifteen seconds. The first snapshot of a new subscription brings the view back
online and resets the delay. `r` still fetches on demand while the view waits,
and `q` or `Escape` quit immediately.

### Pub-sub updates

The live view does not poll. The service publishes notifications over a private
ZeroMQ Unix socket, and the view fetches a complete snapshot over HTTP when a
notification shows that its data is out of date:

1. The service binds `ipc://$XDG_RUNTIME_DIR/code-search-local/<digest>.sock`,
   where the digest identifies the storage root. Without `XDG_RUNTIME_DIR`, the
   directory is `/tmp/code-search-local-<uid>/code-search-local`; when that path
   would be too long for a Unix socket, `/tmp/csl-<uid>` is used. The directory
   must belong to the user (mode `0700`); the socket is mode `0600`.
2. Every state change (job progress, index commits, searches, cache counters,
   model loads) increments the snapshot's `sequence` and publishes an event
   carrying its type, project, `daemon_id` and `sequence`. Events are
   notifications only; data always comes from a fresh snapshot.
3. The view subscribes before it fetches its first snapshot, so a change made in
   between is not lost.
4. The service sends a heartbeat with its `daemon_id` and latest `sequence`
   every second.
5. A message with a higher `sequence`, a different `daemon_id` (the service
   restarted), or any message while the view is offline makes the view fetch a
   new snapshot. Messages that are already reflected in the displayed snapshot
   are ignored.
6. Queues are bounded (256 messages). If notifications are dropped under load,
   the next heartbeat's higher `sequence` reveals the gap and the view
   resynchronises with a complete snapshot.
7. When no message arrives for three seconds, the view keeps the last snapshot,
   marks it offline, and keeps listening. ZeroMQ reconnects to the socket by
   itself; the first heartbeat of the running or restarted service brings the
   view back online.

When a fetch fails because the service cannot be reached, the CLI reads the
persisted database instead, so the view shows an offline snapshot rather than an
error. Other failures follow the
[recovery after errors](#recovery-after-errors).

### Offline snapshots

The service persists the snapshot after every change in
`<storage>/state.sqlite3`. An offline snapshot reads that database read-only and
marks it `online: false`. Counters, jobs, totals and per-path history are
therefore available while the service is stopped, but they are historical:
`model_resident` and the jobs show the last recorded state, not a live reading.
Jobs that were still queued or running when the service stopped are recorded as
`interrupted` when the service starts again. Databases written before per-path
statistics existed have no top paths, and projects recorded before the hit/miss
counters existed show them as zero.

## Search hit and miss statistics

Every search through the CLI `search` command, the `search_code` MCP tool or
`POST /api/v1/search` updates its project's counters, in the same SQLite
transaction as the [per-path statistics](#per-path-statistics).
`find_similar_code` is not counted. Requests rejected before the search runs (an
unregistered project, an empty query or a result count outside 1–100) are not
counted. A search that starts but raises an error is counted in `searches` and
`search_failures`, for example when the project has no committed index yet or
its model changed since indexing.

Scores are cosine similarities between the query and chunk embeddings, from −1.0
to 1.0; higher is more similar. The statistics define three hit rates:

| Rate              | Hit                                                                         | Miss                                                            | Counters                                                                         |
| ----------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Relevance         | A successful search whose top result scored at least `search_hit_min_score` | A top score below the threshold, no results, or a failed search | `search_relevance_hits`, `search_relevance_misses`, `search_relevance_hit_ratio` |
| Non-empty results | A search that returned at least one result                                  | No results, or a failed search                                  | `search_result_hits`, `search_result_misses`, `search_result_hit_ratio`          |
| Query cache       | The query's embedding was found in the embedding cache                      | The model had to embed the query                                | `query_cache_hits`, `query_cache_misses`, `query_cache_hit_ratio`                |

- **Relevance threshold.** `search_hit_min_score` defaults to `0.5` and accepts
  −1.0 to 1.0. Set it with `--search-hit-min-score` on `setup` (persisted) or
  `serve`, with `CODE_SEARCH_SEARCH_HIT_MIN_SCORE`, or in the JSON
  configuration; `doctor` shows the resolved value. The service reads it at
  startup and records it in `shared.search_hit_min_score`. Each search is
  classified with the threshold in effect when it ran; changing the threshold
  does not recompute earlier counters. A suitable threshold depends on the
  model: compare it with the scores that `search` prints and with
  `last_search_top_score`.
- **Non-empty results.** `search_zero_results` counts successful searches that
  returned nothing, for example because metadata filters excluded every chunk or
  the index was cleared. Failed searches are counted in `search_failures`
  instead.
- **Query cache.** The embedding cache (`<storage>/embedding-cache.sqlite3`) is
  keyed by model, revision, encoding, dimension, purpose and exact text. It is
  shared by all projects and survives restarts, so repeating an identical query,
  in any project, is a hit. Searches that fail before the query is embedded do
  not change these counters. `cache_hits`, `cache_misses` and `cache_hit_ratio`
  count every embedding purpose, including document chunks during indexing.

Each ratio is `hits / (hits + misses)`. The JSON reports `0.0` before any hit or
miss; the terminal UI shows `—`. Every project also records `last_search_at` and
`last_search_top_score` (`null` when its last search returned nothing or
failed).

Per-project counters and ratios are in `projects.<root>`, together with
`project_id` (the SHA-256 of the canonical root, as used by the
`code-search-local://stats/{project_id}` resource). `totals` counts the
registered `projects` and sums `files`, `chunks`, `searches`, `search_failures`,
`search_zero_results` and every hit/miss pair over all registered projects, with
each pair's ratio, including `cache_hit_ratio`. `totals` always covers every
project, also when `--project` or the `project` query parameter filters the rest
of the snapshot.

## Per-path statistics

For every successful search that returns results, the service updates one row
per distinct file in the results. The rows live in the `search_paths` table of
`<storage>/state.sqlite3`:

| Value               | Meaning                                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------------------- |
| `path`              | Project-relative file path                                                                           |
| `appearances`       | Searches whose results included the file, counted once per search however many of its chunks matched |
| `hits`              | Of those, searches in which at least one of its returned chunks scored at least the threshold        |
| `misses`            | `appearances − hits`, computed when read                                                             |
| `hit_ratio`         | `hits / appearances`, computed when read; `0.0` for a file never returned                            |
| `top_ranked`        | Searches in which one of its chunks was the first result                                             |
| `chunk_appearances` | Total of its chunks across all those results                                                         |
| `best_score`        | Highest score any of its chunks received                                                             |
| `last_seen_at`      | Time of the latest search that returned it                                                           |

- Failed searches and searches without results add no rows.
- The counts depend on how many results clients request: a file can only appear
  within the top `k` results of a search.
- History is retained. Clearing an index with `clear_index`, reindexing,
  rebuilding and restarting keep every counter and path row; only the index
  itself is discarded.
- Rows of deleted or newly excluded files are kept too. The **top paths** of a
  project (`top_paths` in the snapshot, and the terminal table) are read from
  this history and can therefore include files that are no longer indexed.
- `GET /api/v1/paths?project=<root>` reports the files of the committed
  generation instead: every indexed file, sorted by path, with its chunk count
  (`chunks`) and these values, using zeros and `null` for files that no search
  has returned. History of files outside the committed generation is omitted
  there, and a project without a committed index returns `generation: null` with
  no paths.

## Troubleshooting

| Symptom                                                                                       | What to check                                                                                                                                                                                                                                      |
| --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Service is not configured; run code-search-local setup`                                      | The storage directory has no service token. Check that `CODE_SEARCH_STORAGE` or `--storage` selects the storage the service uses; `code-search-local doctor` shows the resolved settings.                                                          |
| Offline snapshot although the service runs                                                    | The CLI resolves a different port or storage than the service. Compare `doctor` with the service's configuration and check `code-search-local service status`.                                                                                     |
| `Project is not registered: …`                                                                | Use the exact project root that was indexed. `stats` without `--project` lists every registered root; parent and child directories are separate projects.                                                                                          |
| `--json cannot be used with --live`                                                           | Choose one output: JSON for programs, the live view for people.                                                                                                                                                                                    |
| Live view turns offline a few seconds after it starts or after `r`, although the service runs | The view and the service compute different socket paths, usually because one of them runs without `XDG_RUNTIME_DIR` (for example over SSH). Run the view with the same value as the service, normally `export XDG_RUNTIME_DIR=/run/user/$(id -u)`. |
| Live view shows repeated error notifications and stays offline                                | Each notification is one failed attempt to follow the service; the view retries by itself, at most every fifteen seconds. Resolve the reported error, such as an unreadable database; the next attempt brings the view back online.                |
| Rates show `—`                                                                                | The project has no searches, or no query embedding has been looked up yet.                                                                                                                                                                         |
| Relevance rate stays near zero                                                                | The threshold may be too high for the model. Compare `last_search_top_score` and the `search` output scores with `search_hit_min_score`, then rerun setup with another `--search-hit-min-score`.                                                   |
| Query cache rate is low                                                                       | Only identical query text with the same model is a hit; distinct questions are expected misses.                                                                                                                                                    |
| Top paths list a file that no longer exists                                                   | Expected: per-path history outlives the file. `GET /api/v1/paths` lists only currently indexed files.                                                                                                                                              |
| `--live requires a terminal on stdout`                                                        | The live view was redirected or piped. Run it in a terminal; for a file or a pipe, omit `--live` for the plain-text report, or use `--json` for programs.                                                                                          |
| Plain-text report is too narrow or too wide                                                   | Without a terminal, the width is `COLUMNS` or 160 columns. Set it explicitly, for example `COLUMNS=220 code-search-local stats > stats.txt`.                                                                                                       |
