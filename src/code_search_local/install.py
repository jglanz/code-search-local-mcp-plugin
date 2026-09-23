"""Persistent backend environments and user-scoped service/client registration."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, replace
from importlib.resources import files
from pathlib import Path

from . import __version__
from .config import config_path
from .service import token_for
from .storage import ServiceLock, atomic_json

SERVICE = "code-search-local.service"


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def uv_executable():
    from uv import find_uv_bin

    return find_uv_bin()


def select_runtime(backend):
    if backend != "auto":
        return "cpu" if backend == "mps" else backend
    if platform.system() == "Darwin":
        return "cpu"
    if shutil.which("nvidia-smi"):
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True)
        if result.returncode == 0 and "GPU" in result.stdout:
            return "cuda"
    if any(
        path.read_text().strip() == "0x1002"
        for path in Path("/sys/class/drm").glob("card*/device/vendor")
    ):
        return "rocm"
    return "cpu"


def unit_path():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user" / SERVICE


def systemd_quote(value):
    # ExecStart is parsed by systemd, not a shell. Escape specifiers and dollar expansion.
    return (
        '"'
        + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
        + '"'
    )


def runtime_identity(package_source=None):
    identity = hashlib.sha256((files("code_search_local") / "runtime" / "uv.lock").read_bytes())
    if package_source:
        identity.update(Path(package_source).read_bytes())
    return f"{__version__}-{identity.hexdigest()[:12]}"


def install_runtime(settings, backend, package_source=None):
    resources = files("code_search_local") / "runtime"
    identity = runtime_identity(package_source)
    root = settings.root / "runtimes" / f"{__version__}-{backend}-{identity.split('-')[-1]}"
    python = root / ".venv" / "bin" / "python"
    if (root / "installed.json").exists() and python.exists():
        return python
    root.mkdir(parents=True, exist_ok=True)
    for name in ("pyproject.toml", "uv.lock"):
        (root / name).write_bytes((resources / name).read_bytes())
    (root / "README.md").write_text("Managed code-search-local runtime.\n")
    uv = uv_executable()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV", "PYTHONPATH")
    }
    env["PYTHONNOUSERSITE"] = "1"
    run(
        [
            uv,
            "sync",
            "--project",
            root,
            "--locked",
            "--no-dev",
            "--no-install-project",
            "--extra",
            "server",
            "--extra",
            backend,
            "--python",
            "3.12",
        ],
        env=env,
    )
    source = (
        str(Path(package_source).resolve())
        if package_source
        else f"code-search-local=={__version__}"
    )
    run([uv, "pip", "install", "--python", python, "--no-deps", source], env=env)
    atomic_json(root / "installed.json", {"version": __version__, "backend": backend})
    return python


def register_clients(settings, client):
    token = token_for(settings.root)
    endpoint = settings.url + "/mcp"
    if client in ("claude", "both"):
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude CLI is not installed; install it and rerun setup --client claude"
            )
        # Let Claude own its schema, but keep a private rollback copy across remove/add.
        config = (
            Path(os.environ["CLAUDE_CONFIG_DIR"]) / ".claude.json"
            if os.environ.get("CLAUDE_CONFIG_DIR")
            else Path.home() / ".claude.json"
        )
        previous = config.read_text() if config.exists() else None
        if previous is not None:
            atomic_text(config.with_name(config.name + ".code-search-local.bak"), previous)
        try:
            subprocess.run(
                ["claude", "mcp", "remove", "code-search-local", "--scope", "user"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            run(
                [
                    "claude",
                    "mcp",
                    "add",
                    "--scope",
                    "user",
                    "--transport",
                    "http",
                    "code-search-local",
                    endpoint,
                    "--header",
                    f"Authorization: Bearer {token}",
                ],
                stdout=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            if previous is not None:
                atomic_text(config, previous)
            raise
    if client in ("codex", "both"):
        import tomlkit

        path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text() if path.exists() else ""
        document = tomlkit.parse(text)
        servers = document.setdefault("mcp_servers", tomlkit.table())
        servers["code-search-local"] = {
            "url": endpoint,
            "http_headers": {"Authorization": f"Bearer {token}"},
        }
        if path.exists():
            backup = path.with_suffix(".toml.code-search-local.bak")
            backup.write_text(text)
            backup.chmod(0o600)
        atomic_text(path, tomlkit.dumps(document))


def atomic_text(path, content):
    import tempfile

    from .storage import sync_dir

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".code-search-local-")
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def setup(settings, *, client, package_source=None):
    lock = ServiceLock(settings.root, "setup.lock")
    try:
        return _setup(settings, client=client, package_source=package_source)
    finally:
        lock.close()


def _setup(settings, *, client, package_source=None):
    if platform.system() != "Linux":
        raise RuntimeError(
            "User systemd setup currently requires Linux; use serve on other platforms"
        )
    preferred = select_runtime(settings.backend)
    candidates = [preferred]
    if settings.backend == "auto":
        if preferred == "cuda" and any(
            path.read_text().strip() == "0x1002"
            for path in Path("/sys/class/drm").glob("card*/device/vendor")
        ):
            candidates.append("rocm")
        if preferred != "cpu" and settings.allow_fallback:
            candidates.append("cpu")
    choice_path = settings.root / "runtime-choice.json"
    identity = runtime_identity(package_source)
    saved_choice = json.loads(choice_path.read_text()) if choice_path.exists() else {}
    backend = preferred
    if saved_choice.get("identity") == identity and saved_choice.get("settings") == asdict(
        settings
    ):
        backend = saved_choice["backend"]
    python = install_runtime(settings, backend, package_source)
    token_for(settings.root, create=True)
    path = unit_path()
    command = " ".join(
        systemd_quote(value)
        for value in (python, "-m", "code_search_local", "serve", "--storage", settings.root)
    )
    unit = (
        "[Unit]\nDescription=Code Search Local shared model service\nAfter=network.target\n\n"
        "[Service]\nType=simple\n" + f"ExecStart={command}\n"
        f"Environment={systemd_quote('XDG_CONFIG_HOME=' + str(config_path().parent.parent))}\n"
        "Restart=on-failure\nRestartSec=3\nTimeoutStopSec=120\nUMask=0077\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    import asyncio

    from .client import Client

    result = {
        "runtime": str(python.parent.parent),
        "backend": backend,
        "service": str(path),
        "url": settings.url + "/mcp",
    }
    if path.exists() and path.read_text() == unit and config_path().exists():
        saved = json.loads(config_path().read_text())
        if saved == asdict(settings):
            try:
                asyncio.run(Client(settings).request("GET", "/api/v1/health"))
            except (OSError, RuntimeError):
                pass
            else:
                register_clients(settings, client)
                return result
    # Validate actual model inference inside the selected environment before replacing a running service.
    candidate = settings.root / "runtime-candidate.json"
    original_python = python
    for candidate_backend in candidates:
        python = install_runtime(settings, candidate_backend, package_source)
        validation = (
            replace(settings, backend=candidate_backend, cpu_fallback=False)
            if settings.backend == "auto"
            else settings
        )
        atomic_json(candidate, asdict(validation))
        try:
            run(
                [
                    python,
                    "-m",
                    "code_search_local",
                    "doctor",
                    "--settings-file",
                    candidate,
                    "--inference",
                ]
            )
        except subprocess.CalledProcessError:
            if candidate_backend == candidates[-1]:
                raise
            continue
        backend = candidate_backend
        break
    unit = unit.replace(systemd_quote(original_python), systemd_quote(python))
    result.update(runtime=str(python.parent.parent), backend=backend)
    settings.save()
    atomic_text(path, unit)
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", SERVICE])
    run(["systemctl", "--user", "restart", SERVICE])
    deadline = time.monotonic() + 30
    while True:
        try:
            asyncio.run(Client(settings).request("GET", "/api/v1/health"))
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Service did not become healthy; inspect journalctl --user -u code-search-local"
                ) from None
            time.sleep(0.25)
    atomic_json(
        choice_path, {"identity": identity, "settings": asdict(settings), "backend": backend}
    )
    register_clients(settings, client)
    return result


def service_action(action):
    if action == "uninstall":
        run(["systemctl", "--user", "disable", "--now", SERVICE])
        unit_path().unlink(missing_ok=True)
        run(["systemctl", "--user", "daemon-reload"])
    else:
        run(["systemctl", "--user", action, SERVICE])
