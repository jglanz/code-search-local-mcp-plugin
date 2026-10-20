"""Required physical-device acceptance lane; no fake model or silent fallback."""

import os
from pathlib import Path

import numpy as np
import pytest

from code_search_local import constants
from code_search_local.config import Settings
from code_search_local.models import SentenceModel
from tests import constants as test_constants


@pytest.mark.gpu
@pytest.mark.real_model
def test_real_embedding_on_requested_gpu(tmp_path):
    backend = os.environ.get(test_constants.ENV_CODE_SEARCH_GPU_BACKEND)
    if backend is None:
        pytest.skip("Set CODE_SEARCH_GPU_BACKEND=cuda or rocm in the matching runtime")
    assert backend in (constants.BACKEND_CUDA, constants.BACKEND_ROCM)
    shared = os.environ.get(test_constants.ENV_CODE_SEARCH_MODEL_STORAGE)
    if shared:
        (tmp_path / constants.MODEL_CACHE_DIRECTORY).symlink_to(
            Path(shared).resolve() / constants.MODEL_CACHE_DIRECTORY, target_is_directory=True
        )
    model = SentenceModel(
        Settings(storage=str(tmp_path), backend=backend, cpu_fallback=False), lambda **_: None
    )
    try:
        vectors = model.encode(
            ["def add(a, b): return a + b", "def subtract(a, b): return a - b"],
            constants.KEY_DOCUMENT,
        )
        assert vectors.shape == (2, model.info[constants.KEY_DIMENSION])
        assert np.isfinite(vectors).all()
        np.testing.assert_allclose(
            np.linalg.norm(vectors, axis=1), 1, atol=test_constants.EMBEDDING_NORM_TOLERANCE
        )
        assert model.info[constants.KEY_BACKEND] == backend and model.info[constants.KEY_GPU]
        assert model.info[constants.KEY_FALLBACK_REASON] is None
        assert model.memory() > 0
    finally:
        model.close()
