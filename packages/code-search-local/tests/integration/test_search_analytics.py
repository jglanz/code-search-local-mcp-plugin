"""Search hit/miss analytics per project, per path and in total, through a real engine."""

from collections import Counter

import pytest

from code_search_local import constants
from code_search_local.config import Settings
from code_search_local.engine import Engine
from code_search_local.storage import SEARCH_ANALYTICS_DEFAULTS, State, offline_stats, project_id
from tests import constants as test_constants
from tests.fakes import FakeModel

QUERY = "alpha"
MULTI_SOURCE = (
    "def alpha_one():\n    return 'alpha'\n\n\n"
    "def alpha_two():\n    return 'alpha alpha'\n\n\n"
    "def alpha_three():\n    return 'alpha alpha alpha'\n"
)
OTHER_SOURCE = "def unrelated_beta():\n    return 'beta'\n"
# Values written by one search; cache counters change in a separate model transaction.
SEARCH_COUNTS = (
    constants.KEY_SEARCHES,
    constants.KEY_SEARCH_FAILURES,
    constants.KEY_SEARCH_RELEVANCE_HITS,
    constants.KEY_SEARCH_RELEVANCE_MISSES,
    constants.KEY_SEARCH_RESULT_HITS,
    constants.KEY_SEARCH_RESULT_MISSES,
    constants.KEY_SEARCH_ZERO_RESULTS,
)
SEARCH_COUNTERS = (
    *SEARCH_COUNTS,
    constants.KEY_LAST_SEARCH_AT,
    constants.KEY_LAST_SEARCH_TOP_SCORE,
)


def create_project(root):
    root.mkdir()
    (root / test_constants.PATH_MULTI_PY).write_text(MULTI_SOURCE)
    (root / test_constants.PATH_OTHER_PY).write_text(OTHER_SOURCE)
    return str(root)


def start_engine(tmp_path, threshold=constants.DEFAULT_SEARCH_HIT_MIN_SCORE, **options):
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE),
        watch=False,
        search_hit_min_score=threshold,
    )
    return Engine(settings, model_factory=FakeModel, **options)


@pytest.fixture
def project(tmp_path):
    return create_project(tmp_path / constants.KEY_PROJECT)


@pytest.fixture
def engine(tmp_path):
    value = start_engine(tmp_path)
    yield value
    value.close()


def project_stats(engine, root):
    return engine.state.snapshot(root)[constants.KEY_PROJECTS][root]


def counters(stats, keys=SEARCH_COUNTERS):
    return {key: stats[key] for key in keys}


def path_rows(engine, root):
    return {row[constants.KEY_PATH]: row for row in engine.state.search_paths(root)}


def test_threshold_hit_aggregates_each_path_once(engine, project):
    engine.index(project)
    results = engine.search(project, QUERY)[constants.KEY_RESULTS]
    assert Counter(result[constants.KEY_RELATIVE_PATH] for result in results) == {
        test_constants.PATH_MULTI_PY: 3,
        test_constants.PATH_OTHER_PY: 1,
    }
    stats = project_stats(engine, project)
    assert counters(stats, SEARCH_COUNTS) == {
        constants.KEY_SEARCHES: 1,
        constants.KEY_SEARCH_FAILURES: 0,
        constants.KEY_SEARCH_RELEVANCE_HITS: 1,
        constants.KEY_SEARCH_RELEVANCE_MISSES: 0,
        constants.KEY_SEARCH_RESULT_HITS: 1,
        constants.KEY_SEARCH_RESULT_MISSES: 0,
        constants.KEY_SEARCH_ZERO_RESULTS: 0,
    }
    assert stats[constants.KEY_LAST_SEARCH_TOP_SCORE] == results[0][constants.KEY_SCORE]
    assert stats[constants.KEY_SEARCH_RELEVANCE_HIT_RATIO] == 1.0
    assert stats[constants.KEY_SEARCH_RESULT_HIT_RATIO] == 1.0
    assert stats[constants.KEY_PROJECT_ID] == project_id(project)
    rows = path_rows(engine, project)
    multi, other = rows[test_constants.PATH_MULTI_PY], rows[test_constants.PATH_OTHER_PY]
    assert results[0][constants.KEY_RELATIVE_PATH] == test_constants.PATH_MULTI_PY
    assert (multi[constants.KEY_APPEARANCES], multi[constants.KEY_CHUNK_APPEARANCES]) == (1, 3)
    assert (multi[constants.KEY_HITS], multi[constants.KEY_TOP_RANKED]) == (1, 1)
    assert multi[constants.KEY_BEST_SCORE] == max(
        result[constants.KEY_SCORE]
        for result in results
        if result[constants.KEY_RELATIVE_PATH] == test_constants.PATH_MULTI_PY
    )
    # The unrelated file is returned below the default threshold and never ranks first.
    assert other[constants.KEY_BEST_SCORE] < constants.DEFAULT_SEARCH_HIT_MIN_SCORE
    assert (other[constants.KEY_HITS], other[constants.KEY_MISSES]) == (0, 1)
    assert (other[constants.KEY_TOP_RANKED], other[constants.KEY_HIT_RATIO]) == (0, 0.0)
    assert multi[constants.KEY_LAST_SEEN_AT] == stats[constants.KEY_LAST_SEARCH_AT]
    assert stats[constants.KEY_TOP_PATHS] == [multi, other]


def test_searches_accumulate_and_query_cache_is_split(engine, project):
    engine.index(project)
    before = project_stats(engine, project)
    assert before[constants.KEY_CACHE_MISSES] >= 4
    assert (before[constants.KEY_QUERY_CACHE_HITS], before[constants.KEY_QUERY_CACHE_MISSES]) == (
        0,
        0,
    )
    engine.search(project, QUERY)
    engine.search(project, QUERY, k=1)
    stats = project_stats(engine, project)
    assert (stats[constants.KEY_QUERY_CACHE_HITS], stats[constants.KEY_QUERY_CACHE_MISSES]) == (
        1,
        1,
    )
    assert stats[constants.KEY_QUERY_CACHE_HIT_RATIO] == 0.5
    assert stats[constants.KEY_CACHE_HITS] == before[constants.KEY_CACHE_HITS] + 1
    assert stats[constants.KEY_CACHE_MISSES] == before[constants.KEY_CACHE_MISSES] + 1
    assert (stats[constants.KEY_SEARCHES], stats[constants.KEY_SEARCH_RELEVANCE_HITS]) == (2, 2)
    rows = path_rows(engine, project)
    multi = rows[test_constants.PATH_MULTI_PY]
    assert (multi[constants.KEY_APPEARANCES], multi[constants.KEY_CHUNK_APPEARANCES]) == (2, 4)
    assert (multi[constants.KEY_HITS], multi[constants.KEY_TOP_RANKED]) == (2, 2)
    assert rows[test_constants.PATH_OTHER_PY][constants.KEY_APPEARANCES] == 1
    assert [row[constants.KEY_PATH] for row in stats[constants.KEY_TOP_PATHS]] == [
        test_constants.PATH_MULTI_PY,
        test_constants.PATH_OTHER_PY,
    ]


def test_threshold_miss_counts_nonempty_results(tmp_path, project):
    engine = start_engine(tmp_path, constants.MAX_SEARCH_HIT_MIN_SCORE)
    try:
        engine.index(project)
        results = engine.search(project, QUERY)[constants.KEY_RESULTS]
        assert results[0][constants.KEY_SCORE] < constants.MAX_SEARCH_HIT_MIN_SCORE
        snapshot = engine.state.snapshot(project)
        assert (
            snapshot[constants.KEY_SHARED][constants.KEY_SEARCH_HIT_MIN_SCORE]
            == constants.MAX_SEARCH_HIT_MIN_SCORE
        )
        stats = snapshot[constants.KEY_PROJECTS][project]
        assert stats[constants.KEY_SEARCH_RELEVANCE_HITS] == 0
        assert stats[constants.KEY_SEARCH_RELEVANCE_MISSES] == 1
        assert stats[constants.KEY_SEARCH_RESULT_HITS] == 1
        assert stats[constants.KEY_SEARCH_RELEVANCE_HIT_RATIO] == 0.0
        assert all(row[constants.KEY_HITS] == 0 for row in engine.state.search_paths(project))
    finally:
        engine.close()


def test_zero_results_and_clear_keeps_history(engine, project):
    engine.index(project)
    filters = {constants.KEY_RELATIVE_PATH: test_constants.PATH_MISSING_PY}
    assert engine.search(project, QUERY, filters=filters)[constants.KEY_RESULTS] == []
    stats = project_stats(engine, project)
    assert stats[constants.KEY_SEARCH_ZERO_RESULTS] == 1
    assert stats[constants.KEY_SEARCH_RESULT_MISSES] == 1
    assert stats[constants.KEY_SEARCH_RELEVANCE_MISSES] == 1
    assert stats[constants.KEY_LAST_SEARCH_TOP_SCORE] is None
    assert engine.state.search_paths(project) == []
    engine.search(project, QUERY)
    history = path_rows(engine, project)
    engine.clear(project)
    assert engine.search(project, QUERY)[constants.KEY_RESULTS] == []
    stats = project_stats(engine, project)
    assert stats[constants.KEY_SEARCHES] == 3
    assert stats[constants.KEY_SEARCH_ZERO_RESULTS] == 2
    assert stats[constants.KEY_SEARCH_FAILURES] == 0
    assert stats[constants.KEY_SEARCH_RESULT_HITS] == 1
    assert path_rows(engine, project) == history


def test_failed_search_counts_as_miss(engine, project):
    engine._register(project)
    with pytest.raises(ValueError, match="no committed index"):
        engine.search(project, QUERY)
    stats = project_stats(engine, project)
    assert counters(stats, SEARCH_COUNTS) == {
        constants.KEY_SEARCHES: 1,
        constants.KEY_SEARCH_FAILURES: 1,
        constants.KEY_SEARCH_RELEVANCE_HITS: 0,
        constants.KEY_SEARCH_RELEVANCE_MISSES: 1,
        constants.KEY_SEARCH_RESULT_HITS: 0,
        constants.KEY_SEARCH_RESULT_MISSES: 1,
        constants.KEY_SEARCH_ZERO_RESULTS: 0,
    }
    assert stats[constants.KEY_LAST_SEARCH_AT] is not None
    assert stats[constants.KEY_LAST_SEARCH_TOP_SCORE] is None
    assert engine.state.search_paths(project) == []


def test_failed_path_upsert_rolls_back_search_counters(engine, project, monkeypatch):
    engine.index(project)
    engine.search(project, QUERY)
    before, rows = counters(project_stats(engine, project)), path_rows(engine, project)
    original = State.record_search_paths

    def fail_after_upsert(state, *args):
        original(state, *args)
        raise OSError("disk full while recording paths")

    monkeypatch.setattr(State, "record_search_paths", fail_after_upsert)
    with pytest.raises(OSError, match="recording paths"):
        engine.search(project, QUERY)
    assert counters(project_stats(engine, project)) == before
    assert path_rows(engine, project) == rows
    persisted = offline_stats(engine.settings.root, project)[constants.KEY_PROJECTS][project]
    assert counters(persisted) == before


def test_totals_cover_every_project_before_filtering(tmp_path, engine, project):
    second = create_project(tmp_path / test_constants.PATH_SECOND_PROJECT)
    engine.index(project)
    engine.index(second)
    engine.search(project, QUERY)
    engine.search(second, QUERY, filters={constants.KEY_RELATIVE_PATH: test_constants.PATH_X_PY})
    snapshot = engine.state.snapshot()
    totals = snapshot[constants.KEY_TOTALS]
    projects = snapshot[constants.KEY_PROJECTS].values()
    assert totals[constants.KEY_PROJECTS] == 2
    for key in (constants.KEY_FILES, constants.KEY_CHUNKS, constants.KEY_CACHE_MISSES):
        assert totals[key] == sum(stats[key] for stats in projects)
    assert (totals[constants.KEY_SEARCHES], totals[constants.KEY_SEARCH_ZERO_RESULTS]) == (2, 1)
    assert totals[constants.KEY_SEARCH_RESULT_HIT_RATIO] == 0.5
    assert totals[constants.KEY_SEARCH_RELEVANCE_HIT_RATIO] == 0.5
    filtered = engine.state.snapshot(second)
    assert list(filtered[constants.KEY_PROJECTS]) == [second]
    assert filtered[constants.KEY_TOTALS] == totals
    assert filtered[constants.KEY_PROJECTS][second][constants.KEY_TOP_PATHS] == []


def test_legacy_state_without_search_analytics(tmp_path, project):
    engine = start_engine(tmp_path)
    try:
        engine.index(project)
        with engine.state.edit() as value:
            for key in SEARCH_ANALYTICS_DEFAULTS:
                value[constants.KEY_PROJECTS][project].pop(key)
            value[constants.KEY_SHARED].pop(constants.KEY_SEARCH_HIT_MIN_SCORE)
    finally:
        engine.close()
    engine = start_engine(tmp_path, constants.MIN_SEARCH_HIT_MIN_SCORE, recover=False)
    try:
        persisted = engine.state.value[constants.KEY_PROJECTS][project]
        assert not SEARCH_ANALYTICS_DEFAULTS.keys() & persisted.keys()
        stats = project_stats(engine, project)
        assert counters(stats, SEARCH_ANALYTICS_DEFAULTS) == SEARCH_ANALYTICS_DEFAULTS
        assert stats[constants.KEY_QUERY_CACHE_HIT_RATIO] == 0.0
        engine.search(project, QUERY)
        stats = project_stats(engine, project)
        assert stats[constants.KEY_SEARCH_RELEVANCE_HITS] == 1
        assert stats[constants.KEY_QUERY_CACHE_MISSES] == 1
        assert (
            engine.state.snapshot()[constants.KEY_SHARED][constants.KEY_SEARCH_HIT_MIN_SCORE]
            == constants.MIN_SEARCH_HIT_MIN_SCORE
        )
    finally:
        engine.close()
