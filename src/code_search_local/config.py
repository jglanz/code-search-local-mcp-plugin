"""Configuration shared by the lightweight CLI and the model service."""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from code_search_local import constants

BACKENDS = (
    constants.BACKEND_AUTO,
    constants.BACKEND_CPU,
    constants.BACKEND_CUDA,
    constants.BACKEND_ROCM,
    constants.BACKEND_MPS,
)


def loopback_hosts(port):
    hosts = (
        constants.LOOPBACK_IPV4,
        constants.LOOPBACK_HOSTNAME,
        constants.IPV6_HOST_TEMPLATE.format(host=constants.LOOPBACK_IPV6),
    )
    return [constants.HOST_PORT_TEMPLATE.format(host=host, port=port) for host in hosts]


def data_dir() -> Path:
    return (
        Path(
            os.environ.get(
                constants.ENV_CODE_SEARCH_STORAGE,
                str(Path.home() / constants.PATH_CLAUDE_CODE_SEARCH),
            )
        )
        .expanduser()
        .resolve()
    )


def config_path() -> Path:
    base = Path(os.environ.get(constants.ENV_XDG_CONFIG_HOME, Path.home() / constants.PATH_CONFIG))
    return base / constants.APPLICATION_NAME / constants.PATH_CONFIG_JSON


def canonical_project(value: str | Path, *, absolute: bool = False) -> str:
    path = Path(value).expanduser()
    if absolute and not path.is_absolute():
        raise ValueError("project_path must be an absolute path to the project root")
    return str(path.resolve())


@dataclass(frozen=True)
class Settings:
    storage: str = ""
    backend: str = constants.BACKEND_AUTO
    gpu_index: int = constants.DEFAULT_GPU_INDEX
    cpu_fallback: bool | None = None
    model: str = constants.DEFAULT_MODEL_ID
    revision: str = constants.DEFAULT_MODEL_REVISION
    host: str = constants.LOOPBACK_IPV4
    port: int = constants.DEFAULT_SERVICE_PORT
    project_workers: int = constants.DEFAULT_PROJECT_WORKERS
    chunk_workers: int = constants.DEFAULT_CHUNK_WORKERS
    model_batch_size: int = constants.DEFAULT_MODEL_BATCH_SIZE
    max_pending_jobs: int = constants.DEFAULT_MAX_PENDING_JOBS
    max_file_bytes: int = constants.DEFAULT_MAX_FILE_BYTES
    watch: bool = True
    offline: bool = False

    def __post_init__(self):
        if not self.storage:
            object.__setattr__(self, constants.KEY_STORAGE, str(data_dir()))
        if self.backend not in BACKENDS:
            raise ValueError(f"Unsupported backend: {self.backend}")
        if self.host not in (
            constants.LOOPBACK_IPV4,
            constants.LOOPBACK_IPV6,
            constants.LOOPBACK_HOSTNAME,
        ):
            raise ValueError("The local service must bind to a loopback address")
        if (
            not constants.MIN_SERVICE_PORT <= self.port <= constants.MAX_SERVICE_PORT
            or self.gpu_index < 0
        ):
            raise ValueError("Invalid port or GPU index")
        for name in (
            constants.KEY_PROJECT_WORKERS,
            constants.KEY_CHUNK_WORKERS,
            constants.KEY_MODEL_BATCH_SIZE,
            constants.KEY_MAX_PENDING_JOBS,
            constants.KEY_MAX_FILE_BYTES,
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")

    @property
    def root(self) -> Path:
        return Path(self.storage).expanduser().resolve()

    @property
    def url(self) -> str:
        host = (
            constants.IPV6_HOST_TEMPLATE.format(host=self.host) if ":" in self.host else self.host
        )
        return constants.HTTP_URL_TEMPLATE.format(host=host, port=self.port)

    @property
    def allow_fallback(self) -> bool:
        return (
            self.backend == constants.BACKEND_AUTO
            if self.cpu_fallback is None
            else self.cpu_fallback
        )

    @classmethod
    def load(cls, **overrides):
        path = config_path()
        values = json.loads(path.read_text()) if path.exists() else {}
        for field in fields(cls):
            value = os.environ.get(constants.CODE_SEARCH_ENV_PREFIX + field.name.upper())
            if value is not None:
                default = getattr(cls(), field.name)
                if isinstance(default, bool) or field.name == constants.KEY_CPU_FALLBACK:
                    if value.lower() not in (
                        constants.ENV_ENABLED,
                        constants.ENV_DISABLED,
                        constants.BOOLEAN_TRUE,
                        constants.BOOLEAN_FALSE,
                        constants.BOOLEAN_YES,
                        constants.BOOLEAN_NO,
                    ):
                        raise ValueError(f"Invalid boolean for {field.name}: {value}")
                    value = value.lower() in (
                        constants.ENV_ENABLED,
                        constants.BOOLEAN_TRUE,
                        constants.BOOLEAN_YES,
                    )
                elif isinstance(default, int):
                    value = int(value)
                values[field.name] = value
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)

    def save(self):
        from .storage import atomic_json

        atomic_json(config_path(), asdict(self), mode=constants.PRIVATE_FILE_MODE)
