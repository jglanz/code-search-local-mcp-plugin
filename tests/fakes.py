"""Explicit deterministic test double. Production never imports this module."""

import hashlib
import re
import threading

import numpy as np


class FakeModel:
    instances = []

    def __init__(self, settings, report):
        self.owner = threading.get_ident()
        self.calls = []
        self.closed = False
        self.info = {
            "model": settings.model,
            "revision": "fixture-revision",
            "encoding": {"normalize": True, "format_version": 1},
            "dimension": 64,
            "backend": "cpu",
            "device": "cpu",
            "gpu": None,
            "fallback_reason": None,
        }
        self.instances.append(self)
        report(model_acquisitions=1, model_downloads=1, model_loads=1)

    def encode(self, texts, purpose):
        assert threading.get_ident() == self.owner
        self.calls.append((texts, purpose))
        result = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in re.findall(r"[a-z]+", text.lower()):
                result[row, int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1
            result[row] /= max(np.linalg.norm(result[row]), 1)
        return result

    def memory(self):
        assert threading.get_ident() == self.owner
        return 0

    def close(self):
        assert threading.get_ident() == self.owner
        self.closed = True
