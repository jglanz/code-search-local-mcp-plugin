"""The build-time API model generator and the Hatch build hook that runs it."""

import json
import shutil
import sys
from importlib.util import module_from_spec, spec_from_file_location

import yaml

from code_search_local import constants
from scripts.api_models import (
    DOCUMENT_FILENAME,
    MODELS_FILENAME,
    ApiModelsBuildHook,
    generate_api_models,
)
from tests import constants as test_constants

SPEC = test_constants.REPOSITORY_ROOT / test_constants.PATH_OPENAPI_SPEC


def test_generation_is_reproducible(tmp_path, monkeypatch):
    first = generate_api_models(SPEC, tmp_path / test_constants.PATH_FIRST)
    second = generate_api_models(SPEC, tmp_path / test_constants.PATH_SECOND)
    assert [path.name for path in first] == [path.name for path in second]
    for left, right in zip(first, second):
        assert left.read_bytes() == right.read_bytes()
    modified = [path.stat().st_mtime_ns for path in first]
    assert generate_api_models(SPEC, tmp_path / test_constants.PATH_FIRST) == first
    assert [path.stat().st_mtime_ns for path in first] == modified
    document, models = first
    assert json.loads(document.read_text()) == yaml.safe_load(SPEC.read_text())
    specification = spec_from_file_location(test_constants.GENERATED_MODELS_MODULE, models)
    module = module_from_spec(specification)
    # Pydantic resolves postponed annotations through the module registry.
    monkeypatch.setitem(sys.modules, test_constants.GENERATED_MODELS_MODULE, module)
    specification.loader.exec_module(module)
    assert module.PathsResponse.model_json_schema()


def build_data(tmp_path, target, version, *, webapp):
    """Run the hook against a minimal source tree and return its forced inclusions."""
    root = tmp_path / test_constants.PATH_HOOK_ROOT
    spec = root / test_constants.PATH_OPENAPI_SPEC
    spec.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SPEC, spec)
    dist = root / test_constants.PATH_WEBAPP_DIST
    if webapp:
        dist.mkdir(parents=True, exist_ok=True)
        (dist / constants.PATH_INDEX_HTML).write_text(test_constants.WEBAPP_INDEX_SOURCE)
    data = {test_constants.KEY_FORCE_INCLUDE: {}}
    hook = ApiModelsBuildHook(
        str(root), {}, None, None, str(tmp_path / test_constants.PATH_HOOK_OUTPUT), target
    )
    hook.initialize(version, data)
    return root, data[test_constants.KEY_FORCE_INCLUDE]


def test_wheel_hook_bundles_generated_models_and_built_webapp(tmp_path):
    root, included = build_data(
        tmp_path,
        test_constants.HOOK_TARGET_WHEEL,
        test_constants.HOOK_VERSION_STANDARD,
        webapp=True,
    )
    api = root / test_constants.PATH_SRC_CODE_SEARCH_LOCAL_API
    assert included == {
        str(api / DOCUMENT_FILENAME): test_constants.WHEEL_API_OPENAPI_JSON,
        str(api / MODELS_FILENAME): test_constants.WHEEL_API_MODELS_PY,
        str(root / test_constants.PATH_WEBAPP_DIST): test_constants.WHEEL_WEBAPP_DIRECTORY,
    }
    assert all((api / name).is_file() for name in (DOCUMENT_FILENAME, MODELS_FILENAME))


def test_hook_without_webapp_and_for_editable_and_sdist_builds(tmp_path):
    root, included = build_data(
        tmp_path,
        test_constants.HOOK_TARGET_WHEEL,
        test_constants.HOOK_VERSION_STANDARD,
        webapp=False,
    )
    assert test_constants.WHEEL_WEBAPP_DIRECTORY not in included.values()
    assert test_constants.WHEEL_API_MODELS_PY in included.values()
    root, included = build_data(
        tmp_path,
        test_constants.HOOK_TARGET_WHEEL,
        test_constants.HOOK_VERSION_EDITABLE,
        webapp=True,
    )
    # Editable installs import the generated files from the source tree.
    assert included == {}
    api = root / test_constants.PATH_SRC_CODE_SEARCH_LOCAL_API
    assert all((api / name).is_file() for name in (DOCUMENT_FILENAME, MODELS_FILENAME))
    _, included = build_data(
        tmp_path,
        test_constants.HOOK_TARGET_SDIST,
        test_constants.HOOK_VERSION_STANDARD,
        webapp=True,
    )
    assert included == {
        str(root / test_constants.PATH_WEBAPP_DIST): test_constants.PATH_WEBAPP_DIST
    }
