"""Build assets from the sole dependency declarations before setuptools packages them."""

import shutil
from pathlib import Path

from setuptools import build_meta as backend


def prepare():
    root = Path(__file__).resolve().parents[1]
    target = root / "src" / "code_search_local" / "runtime"
    target.mkdir(exist_ok=True)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(root / name, target / name)
    assets = root / "src" / "code_search_local" / "assets" / "plugin"
    # Rebuild generated resources from canonical sources; removed manifests must not survive.
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(root / "plugins" / "code-search-local", assets)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    prepare()
    return backend.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_sdist(sdist_directory, config_settings=None):
    prepare()
    return backend.build_sdist(sdist_directory, config_settings)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    prepare()
    return backend.build_editable(wheel_directory, config_settings, metadata_directory)


get_requires_for_build_wheel = backend.get_requires_for_build_wheel
get_requires_for_build_sdist = backend.get_requires_for_build_sdist
get_requires_for_build_editable = backend.get_requires_for_build_editable
prepare_metadata_for_build_wheel = backend.prepare_metadata_for_build_wheel
prepare_metadata_for_build_editable = backend.prepare_metadata_for_build_editable
