"""Search analytics settings, CLI options and pure statistics selection."""

import json
import math
import sqlite3
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from code_search_local import constants
from code_search_local.cli import main
from code_search_local.config import Settings, config_path
from code_search_local.storage import (
    HIT_RATIOS,
    State,
    offline_stats,
    project_id,
    select_stats,
)
from tests import constants as test_constants

RATIO_KEYS = tuple(ratio for ratio, _, _ in HIT_RATIOS)


def empty_snapshot(projects):
    return {
        constants.KEY_PROJECTS: projects,
        constants.KEY_JOBS: {},
        constants.KEY_SHARED: {},
    }


def result(path, score):
    return {constants.KEY_RELATIVE_PATH: path, constants.KEY_SCORE: score}


def test_zero_denominators_report_zero_ratios(tmp_path):
    root = str(tmp_path / constants.KEY_PROJECT)
    value = select_stats(empty_snapshot({root: {}}))
    stats = value[constants.KEY_PROJECTS][root]
    assert all(stats[key] == 0.0 for key in RATIO_KEYS)
    assert stats[constants.KEY_TOP_PATHS] == []
    assert stats[constants.KEY_PROJECT_ID] == project_id(root)
    assert stats[constants.KEY_SEARCH_ZERO_RESULTS] == 0
    assert stats[constants.KEY_LAST_SEARCH_TOP_SCORE] is None
    totals = select_stats(empty_snapshot({}))[constants.KEY_TOTALS]
    assert totals[constants.KEY_PROJECTS] == 0
    assert totals[constants.KEY_SEARCHES] == 0
    assert all(totals[key] == 0.0 for key in RATIO_KEYS)


def test_offline_stats_read_recorded_paths_and_limit(tmp_path):
    root = str(tmp_path / constants.KEY_PROJECT)
    state = State(tmp_path)
    many = [
        result(test_constants.SEARCH_PATH_TEMPLATE.format(number=number), score)
        for number, score in enumerate([0.1] * (constants.TOP_PATHS_LIMIT + 2))
    ]
    repeated = many[-1]
    with state.edit() as value:
        value[constants.KEY_PROJECTS][root] = {}
        state.record_search_paths(
            root,
            [
                result(test_constants.PATH_A_PY, 0.2),
                result(test_constants.PATH_BETA_PY, 0.9),
                result(test_constants.PATH_A_PY, 0.6),
                repeated,
            ],
            constants.DEFAULT_SEARCH_HIT_MIN_SCORE,
            test_constants.VALUE_NEW,
        )
    with state.edit():
        state.record_search_paths(
            root, many, constants.DEFAULT_SEARCH_HIT_MIN_SCORE, test_constants.VALUE_SECOND
        )
    every = {row[constants.KEY_PATH]: row for row in state.search_paths(root)}
    assert list(every) == sorted(every)
    assert len(every) == len(many) + 2
    state.close()
    once = sorted(set(every) - {repeated[constants.KEY_RELATIVE_PATH]})
    for selected in (None, root):
        top = offline_stats(tmp_path, selected)[constants.KEY_PROJECTS][root][
            constants.KEY_TOP_PATHS
        ]
        # Most appearances first, then path order, bounded per project.
        assert [row[constants.KEY_PATH] for row in top] == [
            repeated[constants.KEY_RELATIVE_PATH],
            *once[: constants.TOP_PATHS_LIMIT - 1],
        ]
        assert top[0][constants.KEY_APPEARANCES] == 2
    a_py = every[test_constants.PATH_A_PY]
    assert a_py == {
        constants.KEY_PATH: test_constants.PATH_A_PY,
        constants.KEY_APPEARANCES: 1,
        constants.KEY_HITS: 1,
        constants.KEY_MISSES: 0,
        constants.KEY_HIT_RATIO: 1.0,
        constants.KEY_TOP_RANKED: 1,
        constants.KEY_CHUNK_APPEARANCES: 2,
        constants.KEY_BEST_SCORE: 0.6,
        constants.KEY_LAST_SEEN_AT: test_constants.VALUE_NEW,
    }
    assert every[test_constants.PATH_BETA_PY][constants.KEY_TOP_RANKED] == 0
    assert every[many[0][constants.KEY_RELATIVE_PATH]][constants.KEY_HIT_RATIO] == 0.0


def test_offline_stats_without_path_table(tmp_path):
    root = str(tmp_path / constants.KEY_PROJECT)
    # Databases from older versions contain only the snapshot table.
    db = sqlite3.connect(tmp_path / constants.PATH_STATE_SQLITE3)
    db.execute(constants.SQL_CREATE_STATE)
    snapshot = empty_snapshot({root: {constants.KEY_FILES: 2, constants.KEY_SEARCHES: 3}})
    db.execute(constants.SQL_SAVE_STATE, (json.dumps(snapshot),))
    db.commit()
    db.close()
    value = offline_stats(tmp_path, root)
    assert value[constants.KEY_PROJECTS][root][constants.KEY_TOP_PATHS] == []
    assert value[constants.KEY_TOTALS][constants.KEY_FILES] == 2
    assert value[constants.KEY_TOTALS][constants.KEY_SEARCHES] == 3
    assert not value[constants.KEY_ONLINE]


def test_threshold_setting_bounds_and_float_environment(monkeypatch):
    assert Settings().search_hit_min_score == constants.DEFAULT_SEARCH_HIT_MIN_SCORE
    for invalid in (
        constants.MIN_SEARCH_HIT_MIN_SCORE - 1,
        test_constants.OUT_OF_RANGE_SEARCH_HIT_MIN_SCORE,
        math.nan,
    ):
        with pytest.raises(ValueError, match=constants.KEY_SEARCH_HIT_MIN_SCORE):
            Settings(search_hit_min_score=invalid)
    monkeypatch.setenv(
        test_constants.ENV_CODE_SEARCH_SEARCH_HIT_MIN_SCORE,
        str(test_constants.SAMPLE_SEARCH_HIT_MIN_SCORE),
    )
    assert Settings.load().search_hit_min_score == test_constants.SAMPLE_SEARCH_HIT_MIN_SCORE
    monkeypatch.setenv(
        test_constants.ENV_CODE_SEARCH_SEARCH_HIT_MIN_SCORE,
        str(test_constants.OUT_OF_RANGE_SEARCH_HIT_MIN_SCORE),
    )
    with pytest.raises(ValueError, match=constants.KEY_SEARCH_HIT_MIN_SCORE):
        Settings.load()
    monkeypatch.setenv(test_constants.ENV_CODE_SEARCH_SEARCH_HIT_MIN_SCORE, "not-a-number")
    with pytest.raises(ValueError, match="float"):
        Settings.load()
    failed = CliRunner().invoke(main, [constants.COMMAND_DOCTOR])
    assert failed.exit_code == 1
    assert "float" in failed.stderr


def test_threshold_option_reaches_doctor_setup_and_serve(monkeypatch):
    from code_search_local import install, service

    option = [
        constants.OPTION_SEARCH_HIT_MIN_SCORE,
        str(test_constants.SAMPLE_SEARCH_HIT_MIN_SCORE),
    ]
    runner = CliRunner()
    doctor = runner.invoke(main, [constants.COMMAND_DOCTOR, *option])
    assert doctor.exit_code == 0, doctor.output
    assert (
        json.loads(doctor.stdout)[constants.KEY_SETTINGS][constants.KEY_SEARCH_HIT_MIN_SCORE]
        == test_constants.SAMPLE_SEARCH_HIT_MIN_SCORE
    )
    rejected = runner.invoke(
        main,
        [
            constants.COMMAND_DOCTOR,
            constants.OPTION_SEARCH_HIT_MIN_SCORE,
            str(test_constants.OUT_OF_RANGE_SEARCH_HIT_MIN_SCORE),
        ],
    )
    assert rejected.exit_code == 2
    assert constants.OPTION_SEARCH_HIT_MIN_SCORE in rejected.stderr

    def save_settings(settings, **kwargs):
        # The installer persists the effective settings before starting the service.
        settings.save()
        return {}

    monkeypatch.setattr(install, "setup", save_settings)
    assert runner.invoke(main, [test_constants.COMMAND_SETUP, *option]).exit_code == 0
    saved = json.loads(config_path().read_text())
    assert saved[constants.KEY_SEARCH_HIT_MIN_SCORE] == test_constants.SAMPLE_SEARCH_HIT_MIN_SCORE
    served = Mock()
    monkeypatch.setattr(service, "serve", served)
    # The service unit passes only --storage; the saved threshold reaches the daemon.
    assert runner.invoke(main, [constants.COMMAND_SERVE]).exit_code == 0
    assert (
        served.call_args.args[0].search_hit_min_score == test_constants.SAMPLE_SEARCH_HIT_MIN_SCORE
    )
