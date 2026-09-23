"""Required physical-device acceptance lane; no fake model or silent fallback."""

import os
from pathlib import Path

import numpy as np
import pytest

from code_search_local.config import Settings
from code_search_local.models import SentenceModel


@pytest.mark.gpu
@pytest.mark.real_model
def test_real_embedding_on_requested_gpu(tmp_path):
    backend = os.environ.get("CODE_SEARCH_GPU_BACKEND")
    if backend is None:
        pytest.skip("Set CODE_SEARCH_GPU_BACKEND=cuda or rocm in the matching runtime")
    assert backend in ("cuda", "rocm")
    shared = os.environ.get("CODE_SEARCH_MODEL_STORAGE")
    if shared:
        (tmp_path / "models").symlink_to(
            Path(shared).resolve() / "models", target_is_directory=True
        )
    model = SentenceModel(
        Settings(storage=str(tmp_path), backend=backend, cpu_fallback=False), lambda **_: None
    )
    try:
        vectors = model.encode(
            ["def add(a, b): return a + b", "def subtract(a, b): return a - b"], "document"
        )
        assert vectors.shape == (2, model.info["dimension"])
        assert np.isfinite(vectors).all()
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
        assert model.info["backend"] == backend and model.info["gpu"]
        assert model.info["fallback_reason"] is None
        assert model.memory() > 0
    finally:
        model.close()
