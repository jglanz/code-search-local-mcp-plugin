"""Explicit deterministic test double. Production never imports this module."""

import hashlib
import re
import threading

import numpy as np

from code_search_local import constants
from tests import constants as test_constants


class FakeModel:
    instances = []

    def __init__(self, settings, report):
        self.owner = threading.get_ident()
        self.calls = []
        self.closed = False
        self.info = {
            constants.KEY_MODEL: settings.model,
            constants.KEY_REVISION: "fixture-revision",
            constants.KEY_ENCODING: {
                constants.KEY_NORMALIZE: True,
                constants.KEY_FORMAT_VERSION: 1,
            },
            constants.KEY_DIMENSION: 64,
            constants.KEY_BACKEND: constants.BACKEND_CPU,
            constants.KEY_DEVICE: constants.BACKEND_CPU,
            constants.KEY_GPU: None,
            constants.KEY_FALLBACK_REASON: None,
        }
        self.instances.append(self)
        report(model_acquisitions=1, model_downloads=1, model_loads=1)

    def encode(self, texts, purpose):
        assert threading.get_ident() == self.owner
        self.calls.append((texts, purpose))
        result = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(test_constants.PATTERN_A_Z, text.lower()):
                result[row, int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1
            result[row] /= max(np.linalg.norm(result[row]), 1)
        return result

    def memory(self):
        assert threading.get_ident() == self.owner
        return 0

    def close(self):
        assert threading.get_ident() == self.owner
        self.closed = True
