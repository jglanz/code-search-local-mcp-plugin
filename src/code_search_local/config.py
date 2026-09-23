"""Configuration shared by the lightweight CLI and the model service."""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

BACKENDS = ("auto", "cpu", "cuda", "rocm", "mps")


def data_dir() -> Path:
    return (
        Path(os.environ.get("CODE_SEARCH_STORAGE", str(Path.home() / ".claude_code_search")))
        .expanduser()
        .resolve()
    )


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "code-search-local" / "config.json"


def canonical_project(value: str | Path, *, absolute: bool = False) -> str:
    path = Path(value).expanduser()
    if absolute and not path.is_absolute():
        raise ValueError("project_path must be an absolute path to the project root")
    return str(path.resolve())


@dataclass(frozen=True)
class Settings:
    storage: str = ""
    backend: str = "auto"
    gpu_index: int = 0
    cpu_fallback: bool | None = None
    model: str = "google/embeddinggemma-300m"
    revision: str = "main"
    host: str = "127.0.0.1"
    port: int = 8000
    project_workers: int = 4
    chunk_workers: int = 4
    model_batch_size: int = 32
    max_pending_jobs: int = 64
    max_file_bytes: int = 2 * 1024 * 1024
    watch: bool = True
    offline: bool = False

    def __post_init__(self):
        if not self.storage:
            object.__setattr__(self, "storage", str(data_dir()))
        if self.backend not in BACKENDS:
            raise ValueError(f"Unsupported backend: {self.backend}")
        if self.host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("The local service must bind to a loopback address")
        if not 1 <= self.port <= 65535 or self.gpu_index < 0:
            raise ValueError("Invalid port or GPU index")
        for name in (
            "project_workers",
            "chunk_workers",
            "model_batch_size",
            "max_pending_jobs",
            "max_file_bytes",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")

    @property
    def root(self) -> Path:
        return Path(self.storage).expanduser().resolve()

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    @property
    def allow_fallback(self) -> bool:
        return self.backend == "auto" if self.cpu_fallback is None else self.cpu_fallback

    @classmethod
    def load(cls, **overrides):
        path = config_path()
        values = json.loads(path.read_text()) if path.exists() else {}
        for field in fields(cls):
            value = os.environ.get(f"CODE_SEARCH_{field.name.upper()}")
            if value is not None:
                default = getattr(cls(), field.name)
                if isinstance(default, bool) or field.name == "cpu_fallback":
                    if value.lower() not in ("1", "0", "true", "false", "yes", "no"):
                        raise ValueError(f"Invalid boolean for {field.name}: {value}")
                    value = value.lower() in ("1", "true", "yes")
                elif isinstance(default, int):
                    value = int(value)
                values[field.name] = value
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    def save(self):
        from .storage import atomic_json

        atomic_json(config_path(), asdict(self), mode=0o600)
