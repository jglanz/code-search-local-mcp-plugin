"""Generated API contract enforcement, per-path analytics and the static web dashboard."""

import dataclasses
import json

import httpx2
import pytest
import yaml

from code_search_local import constants, service
from code_search_local.api import models
from code_search_local.config import Settings
from code_search_local.engine import Engine
from code_search_local.service import create_app, token_for, webapp_directory
from code_search_local.storage import project_id
from tests import constants as test_constants
from tests.fakes import FakeModel

ALPHA_SOURCE = "def alpha():\n    return 'alpha'\n"
BETA_SOURCE = "def beta():\n    return 'beta'\n"
SECURITY_HEADERS = (
    (constants.HEADER_CONTENT_SECURITY_POLICY, constants.WEBAPP_CONTENT_SECURITY_POLICY),
    (constants.HEADER_CONTENT_TYPE_OPTIONS, constants.CONTENT_TYPE_OPTIONS_NOSNIFF),
    (constants.HEADER_REFERRER_POLICY, constants.REFERRER_POLICY_NO_REFERRER),
)


def build_webapp(directory):
    (directory / test_constants.PATH_ASSETS).mkdir(parents=True)
    (directory / constants.PATH_INDEX_HTML).write_text(test_constants.WEBAPP_INDEX_SOURCE)
    (directory / test_constants.PATH_ASSETS / test_constants.PATH_APP_JS).write_text(
        test_constants.WEBAPP_SCRIPT_SOURCE
    )
    return directory


@pytest.fixture
async def api(tmp_path):
    settings = Settings(
        storage=str(tmp_path / test_constants.KEY_STATE),
        watch=False,
        webapp_dir=str(build_webapp(tmp_path / test_constants.PATH_WEBAPP)),
    )
    engine = Engine(settings, model_factory=FakeModel)
    app = create_app(engine, token_for(settings.root, create=True))
    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app), base_url=settings.url
        ) as client:
            yield engine, client
    finally:
        engine.close()


def authorize(engine, client):
    client.headers[constants.KEY_AUTHORIZATION] = constants.HTTP_BEARER + token_for(
        engine.settings.root
    )


@pytest.fixture
def project(tmp_path):
    root = tmp_path / constants.KEY_PROJECT
    root.mkdir()
    (root / test_constants.PATH_BETA_PY).write_text(BETA_SOURCE)
    (root / test_constants.PATH_ALPHA_PY).write_text(ALPHA_SOURCE)
    (root / test_constants.PATH_EMPTY_PY).write_text("")
    return str(root)


def assert_security_headers(response):
    for name, value in SECURITY_HEADERS:
        assert response.headers[name] == value


async def test_stats_and_paths_responses_validate(api, project):
    engine, client = api
    authorize(engine, client)
    job = await client.post(
        constants.INDEX_ENDPOINT,
        json={constants.KEY_DIRECTORY_PATH: project, constants.KEY_WAIT: True},
    )
    assert job.json()[constants.KEY_STATUS] == constants.STATUS_SUCCEEDED
    search = await client.post(
        constants.SEARCH_ENDPOINT,
        json={
            constants.KEY_PROJECT_PATH: project,
            constants.KEY_QUERY: test_constants.VALUE_ALPHA,
            constants.KEY_K: 1,
        },
    )
    assert search.status_code == constants.HTTP_OK
    stats = await client.get(constants.STATS_ENDPOINT)
    assert stats.status_code == constants.HTTP_OK
    snapshot = models.StatsSnapshot.model_validate(stats.json())
    assert snapshot.projects[project].search_result_hits == 1
    assert snapshot.projects[project].top_paths[0].path == test_constants.PATH_ALPHA_PY

    response = await client.get(constants.PATHS_ENDPOINT, params={constants.KEY_PROJECT: project})
    assert response.status_code == constants.HTTP_OK
    body = response.json()
    paths = models.PathsResponse.model_validate(body)
    assert paths.project_path == project
    assert paths.project_id == project_id(project)
    assert paths.generation == snapshot.projects[project].generation
    assert paths.search_hit_min_score == constants.DEFAULT_SEARCH_HIT_MIN_SCORE
    rows = {row[constants.KEY_PATH]: row for row in body[constants.KEY_PATHS]}
    assert list(rows) == sorted(rows)
    assert set(rows) == {
        test_constants.PATH_ALPHA_PY,
        test_constants.PATH_BETA_PY,
        test_constants.PATH_EMPTY_PY,
    }
    alpha = rows[test_constants.PATH_ALPHA_PY]
    assert alpha[constants.KEY_APPEARANCES] == alpha[constants.KEY_TOP_RANKED] == 1
    assert alpha[constants.KEY_CHUNKS] >= 1
    assert alpha[constants.KEY_BEST_SCORE] is not None
    beta = rows[test_constants.PATH_BETA_PY]
    assert beta[constants.KEY_CHUNKS] >= 1
    assert beta[constants.KEY_APPEARANCES] == beta[constants.KEY_MISSES] == 0
    assert beta[constants.KEY_BEST_SCORE] is beta[constants.KEY_LAST_SEEN_AT] is None
    assert rows[test_constants.PATH_EMPTY_PY][constants.KEY_CHUNKS] == 0


async def test_paths_rejects_unknown_projects_and_reports_uncommitted_ones(api, project):
    engine, client = api
    authorize(engine, client)
    for params in ({}, {constants.KEY_PROJECT: project}, {constants.KEY_PROJECT: project[1:]}):
        response = await client.get(constants.PATHS_ENDPOINT, params=params)
        assert response.status_code == constants.HTTP_BAD_REQUEST
        assert models.ErrorResponse.model_validate(response.json()).error
    engine._register(project)
    response = await client.get(constants.PATHS_ENDPOINT, params={constants.KEY_PROJECT: project})
    assert response.status_code == constants.HTTP_OK
    body = response.json()
    assert body[constants.KEY_GENERATION] is None
    assert body[constants.KEY_PATHS] == []


async def test_contract_violations_return_server_error(api, project, monkeypatch, caplog):
    engine, client = api
    authorize(engine, client)
    monkeypatch.setattr(engine, "paths", lambda root: {constants.KEY_PROJECT_PATH: root})
    response = await client.get(constants.PATHS_ENDPOINT, params={constants.KEY_PROJECT: project})
    assert response.status_code == constants.HTTP_INTERNAL_SERVER_ERROR
    assert models.PathsResponse.__name__ in response.json()[constants.KEY_ERROR]
    assert models.PathsResponse.__name__ in caplog.text


async def test_invalid_request_bodies_are_rejected(api, project):
    engine, client = api
    authorize(engine, client)
    search = {constants.KEY_PROJECT_PATH: project, constants.KEY_QUERY: test_constants.VALUE_ALPHA}
    requests = (
        (constants.INDEX_ENDPOINT, {}),
        (
            constants.INDEX_ENDPOINT,
            {constants.KEY_DIRECTORY_PATH: project, test_constants.KEY_UNEXPECTED: True},
        ),
        (
            constants.INDEX_ENDPOINT,
            {
                constants.KEY_DIRECTORY_PATH: project,
                constants.KEY_WAIT: test_constants.VALUE_NOT_A_BOOLEAN,
            },
        ),
        (
            constants.SEARCH_ENDPOINT,
            {**search, constants.KEY_QUERY: test_constants.VALUE_BLANK_QUERY},
        ),
        (
            constants.SEARCH_ENDPOINT,
            {**search, constants.KEY_K: test_constants.SEARCH_LIMIT_BELOW_RANGE},
        ),
        (
            constants.SEARCH_ENDPOINT,
            {**search, constants.KEY_K: test_constants.SEARCH_LIMIT_ABOVE_RANGE},
        ),
        (constants.SEARCH_ENDPOINT, {**search, test_constants.KEY_UNEXPECTED: True}),
        (constants.SEARCH_ENDPOINT, [search]),
    )
    for endpoint, body in requests:
        response = await client.post(endpoint, json=body)
        assert response.status_code == constants.HTTP_BAD_REQUEST, (endpoint, body)
        assert models.ErrorResponse.model_validate(response.json()).error
    response = await client.post(
        constants.SEARCH_ENDPOINT, content=test_constants.VALUE_INVALID_JSON
    )
    assert response.status_code == constants.HTTP_BAD_REQUEST
    assert engine.state.snapshot()[constants.KEY_JOBS] == {}


async def test_openapi_document_requires_the_token(api):
    engine, client = api
    response = await client.get(constants.OPENAPI_ENDPOINT)
    assert response.status_code == constants.HTTP_UNAUTHORIZED
    authorize(engine, client)
    response = await client.get(constants.OPENAPI_ENDPOINT)
    assert response.status_code == constants.HTTP_OK
    spec = test_constants.REPOSITORY_ROOT / test_constants.PATH_OPENAPI_SPEC
    assert response.json() == json.loads(json.dumps(yaml.safe_load(spec.read_text())))
    assert response.json()[test_constants.KEY_OPENAPI].startswith(
        test_constants.VALUE_OPENAPI_VERSION_PREFIX
    )


async def test_webapp_is_public_static_and_secured(api):
    _, client = api
    for endpoint in (constants.ROOT_ENDPOINT, constants.WEBAPP_ENDPOINT):
        response = await client.get(endpoint)
        assert response.status_code == constants.HTTP_TEMPORARY_REDIRECT
        assert response.headers[test_constants.KEY_LOCATION] == constants.WEBAPP_INDEX_ENDPOINT
    # The entry page, directly or for an extensionless client-side route, is always revalidated.
    for endpoint in (
        constants.WEBAPP_INDEX_ENDPOINT,
        test_constants.URL_WEBAPP_INDEX_HTML,
        test_constants.URL_WEBAPP_CLIENT_ROUTE,
    ):
        response = await client.get(endpoint)
        assert response.status_code == constants.HTTP_OK, endpoint
        assert response.headers[test_constants.KEY_CONTENT_TYPE].startswith(
            test_constants.CONTENT_TYPE_HTML
        )
        assert response.text == test_constants.WEBAPP_INDEX_SOURCE
        assert response.headers[constants.HEADER_CACHE_CONTROL] == constants.CACHE_CONTROL_NO_CACHE
        assert_security_headers(response)
    response = await client.get(test_constants.URL_WEBAPP_APP_JS)
    assert response.headers[test_constants.KEY_CONTENT_TYPE].startswith(
        test_constants.CONTENT_TYPE_JAVASCRIPT
    )
    assert response.text == test_constants.WEBAPP_SCRIPT_SOURCE
    assert constants.HEADER_CACHE_CONTROL not in response.headers
    assert_security_headers(response)
    # A missing file is never answered with the entry page, nor is a path outside the build.
    for endpoint in (
        test_constants.URL_WEBAPP_MISSING_ASSET,
        test_constants.URL_WEBAPP_ENCODED_TRAVERSAL,
        test_constants.URL_WEBAPP_ABSOLUTE_PATH,
        test_constants.URL_WEBAPP_NULL_BYTE,
    ):
        response = await client.get(endpoint)
        assert response.status_code == constants.HTTP_NOT_FOUND, endpoint
        assert not response.headers[test_constants.KEY_CONTENT_TYPE].startswith(
            test_constants.CONTENT_TYPE_HTML
        )
        assert response.text != test_constants.WEBAPP_INDEX_SOURCE
        assert_security_headers(response)
    for headers in (
        {constants.KEY_HOST: test_constants.PATH_BAD},
        # A valid Host does not admit a page served from another origin.
        {test_constants.KEY_ORIGIN: test_constants.VALUE_FOREIGN_ORIGIN},
    ):
        response = await client.get(constants.WEBAPP_INDEX_ENDPOINT, headers=headers)
        assert response.status_code == constants.HTTP_FORBIDDEN, headers
    for endpoint in (test_constants.URL_NOT_WEBAPP, constants.PATHS_ENDPOINT):
        assert (await client.get(endpoint)).status_code == constants.HTTP_UNAUTHORIZED


async def test_missing_webapp_build_is_unavailable(api, tmp_path):
    engine, client = api
    empty = tmp_path / test_constants.PATH_EMPTY_WEBAPP
    empty.mkdir()
    engine.settings = dataclasses.replace(engine.settings, webapp_dir=str(empty))
    response = await client.get(constants.WEBAPP_INDEX_ENDPOINT)
    assert response.status_code == constants.HTTP_SERVICE_UNAVAILABLE
    assert "pnpm build" in response.text
    assert_security_headers(response)


def test_webapp_directory_resolution_order(tmp_path, monkeypatch):
    checkout = tmp_path / test_constants.PATH_CHECKOUT_PACKAGES
    installed = tmp_path / test_constants.PATH_INSTALLED_PACKAGE
    explicit = build_webapp(tmp_path / test_constants.PATH_WEBAPP)
    checkout_build = build_webapp(checkout / constants.PATH_CHECKOUT_WEBAPP_DIST)
    installed_build = build_webapp(installed / constants.PATH_INSTALLED_WEBAPP)
    monkeypatch.setattr(service, "CHECKOUT_PACKAGES_DIRECTORY", checkout)
    monkeypatch.setattr(service, "PACKAGE_DIRECTORY", installed)
    assert webapp_directory(Settings(webapp_dir=str(explicit))) == explicit.resolve()
    # Installed layout: a build beside unrelated parent directories is never served.
    assert webapp_directory(Settings()) == installed_build.resolve()
    marker = checkout.parent / constants.PATH_SRC_CODE_SEARCH_LOCAL_INIT_PY
    marker.parent.mkdir(parents=True)
    marker.write_text("")
    assert webapp_directory(Settings()) == checkout_build.resolve()
    (checkout_build / constants.PATH_INDEX_HTML).unlink()
    assert webapp_directory(Settings()) == installed_build.resolve()
    (explicit / constants.PATH_INDEX_HTML).unlink()
    # A configured directory is authoritative even when another build exists.
    assert webapp_directory(Settings(webapp_dir=str(explicit))) is None
    (installed_build / constants.PATH_INDEX_HTML).unlink()
    assert webapp_directory(Settings()) is None
