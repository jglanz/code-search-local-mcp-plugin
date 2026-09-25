#!/usr/bin/env python3
"""Inventory and remove current/legacy Code Search Local installations on Linux.

Review this whole file before using --apply --reviewed. The assistant is authorized
to run ONLY --dry-run. Discovery is read-only; all mutations live in apply_plan().
This standalone script uses only the project's Click, json5 and tomlkit dependencies.
It deliberately does not import or call either installed server's uninstall hooks.
"""

import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import click
import json5
import tomlkit

IDENTITY = re.compile(
    r"(?:code[-_]search[-_]local|claude[-_]context[-_]local|claude[-_]code[-_]search)", re.I
)
ENVIRONMENT = re.compile(r"^(?:CODE_SEARCH_|CLAUDE_CONTEXT_LOCAL_|CLAUDE_CODE_SEARCH_)", re.I)
REGISTRIES = {
    "mcpservers",
    "mcp_servers",
    "mcp",
    "servers",
    "plugins",
    "enabledplugins",
    "marketplaces",
    "extraknownmarketplaces",
    "extensions",
    "dependencies",
    "devdependencies",
}
HARNESSES = (
    ".claude",
    ".codex",
    ".Codex",
    ".agents",
    ".cursor",
    ".windsurf",
    ".codeium",
    ".continue",
    ".gemini",
    ".kiro",
    ".roo",
    ".q",
    ".vscode",
    ".vscode-insiders",
    ".openclaw",
)
CONFIG_APPS = (
    "Claude",
    "Claude-3p",
    "claude",
    "Codex",
    "codex",
    "opencode",
    "Code",
    "Code - Insiders",
    "VSCodium",
    "Cursor",
    "Windsurf",
    "zed",
    "goose",
    "continue",
    "gemini",
    "kiro",
    "openclaw",
)
SKIP = {
    ".git",
    "node_modules",
    ".venv",
    ".venvs",
    "venv",
    "__pycache__",
    "sessions",
    "archived_sessions",
    "transcripts",
    "memories",
    "memory",
    "logs",
    "log",
    "debug",
    "file-history",
    "shell-snapshots",
    "shell_snapshots",
    "plans",
    "tasks",
    "Cache",
    "GPUCache",
    "Code Cache",
    "IndexedDB",
    "Local Storage",
    "Session Storage",
    "Crashpad",
    "Service Worker",
    "WebStorage",
    "blob_storage",
    "attachments",
    "assets",
    "fixtures",
    "tests",
    "examples",
    "history",
    "remote_plugin_catalog",
}
PROJECT_CONFIGS = (
    ".mcp.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".codex/config.toml",
    ".cursor/mcp.json",
    ".windsurf/mcp_config.json",
    ".codeium/windsurf/mcp_config.json",
    ".vscode/mcp.json",
    ".vscode/settings.json",
    ".gemini/settings.json",
    ".kiro/settings/mcp.json",
    ".roo/mcp.json",
    ".continue/config.json",
    ".continue/config.yaml",
    "opencode.json",
    "opencode.jsonc",
    ".opencode/opencode.json",
    ".opencode/opencode.jsonc",
)
MAX_BYTES = 16 * 1024 * 1024
BACKUP_NAME = re.compile(
    r"\.(?:bak\d*|backups?|bkp|old|orig|save)(?:$|[._-])"
    r"|^\.?(?:backups?)(?:$|[-_. ])"
    r"|^\.?saved(?:$|[-_. ]\d)"
    r"|[-_](?:backups?|bak|bkp)(?:$|[-_.]?\d)"
    r"|\.(?:jsonc?|toml|ya?ml|conf)[._-](?:19|20)\d{2}[-_.]?\d{2}[-_.]?\d{2}",
    re.I,
)


def matches(value):
    return isinstance(value, str) and bool(IDENTITY.search(value))


def named(value):
    """An owned artifact/registration name, not an incidental mention in prose."""
    match = IDENTITY.match(value.lstrip("."))
    return bool(
        match
        and (match.end() == len(value.lstrip(".")) or value.lstrip(".")[match.end()] in "-_.@/")
    )


def backup_name(name):
    return (
        bool(BACKUP_NAME.search(name))
        or name.endswith("~")
        or name.lower().endswith((".swp", ".swo", ".swn"))
        or name.startswith("#")
        and name.endswith("#")
    )


def backup_path(path):
    """Ignore backup files/directories and ordinary-looking symlinks into them."""
    path = Path(path)
    return any(backup_name(part) for part in (*path.parts, *path.resolve().parts))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(path):
    info = path.lstat()
    return [info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)]


def source_worktree(path):
    """Recognize clones and linked worktrees (.git can be a directory or a file)."""
    resolved = path.resolve()
    return next(
        (parent for parent in (resolved, *resolved.parents) if (parent / ".git").exists()), None
    )


def distribution_name(metadata):
    return metadata.name.removesuffix(".dist-info").rsplit("-", 1)[0].replace("_", "-")


def manager_executable(name):
    candidate = shutil.which(name) or str(Path(sys.executable).parent / name)
    if Path(candidate).is_file() and os.access(candidate, os.X_OK):
        return candidate
    if name == "uv":
        from uv import find_uv_bin

        return find_uv_bin()
    return None


def readonly(args, *, timeout=15):
    """Read-only commands only. Neither discovery nor --dry-run calls apply_plan."""
    return subprocess.run(args, check=False, capture_output=True, text=True, timeout=timeout)


def contains_reference(value, endpoints=()):
    if isinstance(value, str):
        return matches(value) or value in endpoints
    if isinstance(value, dict):
        return any(
            contains_reference(k, endpoints) or contains_reference(v, endpoints)
            for k, v in value.items()
        )
    if isinstance(value, list):
        return any(contains_reference(item, endpoints) for item in value)
    return False


def registration_reference(value, endpoints=()):
    """Inspect identity/launch fields, not descriptions or an entire mixed marketplace."""
    if isinstance(value, str):
        return contains_reference(value, endpoints)
    if not isinstance(value, dict):
        return False
    return any(
        contains_reference(value.get(key), endpoints)
        for key in (
            "name",
            "id",
            "pluginId",
            "command",
            "args",
            "url",
            "source",
            "repo",
            "repository",
            "installPath",
            "path",
            "serverInfo",
        )
    )


def reference_locations(value, trail=()):
    """Report JSON/TOML field paths, never their potentially sensitive values."""
    if isinstance(value, dict):
        for key, child in value.items():
            location = (*trail, str(key))
            if matches(str(key)):
                yield location
            yield from reference_locations(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from reference_locations(child, (*trail, str(index)))
    elif matches(value):
        yield trail


def entry_match(location, value, endpoints, *, key=None):
    """Explain an exact match without exposing config values, tokens or full commands."""
    trail = [part.lower() for part in location]
    if any("mcp-server-tools-cache" in part for part in trail):
        category = "cached MCP discovery entry"
    elif any(part in {"mcp", "mcpservers", "mcp_servers", "servers"} for part in trail):
        category = "MCP registration"
    elif "hooks" in trail:
        category = "hook"
    elif any(part in {"env", "environment"} for part in trail):
        category = "environment setting"
    elif any(part in {"marketplaces", "extraknownmarketplaces"} for part in trail):
        category = "marketplace catalog entry"
    elif any(
        part in {"plugins", "plugin", "enabledplugins", "marketplaces", "extraknownmarketplaces"}
        for part in trail
    ):
        category = "plugin registration"
    else:
        category = "tool permission or setting"
    fields = []

    def inspect(value, path):
        if isinstance(value, dict):
            for name in (
                "name",
                "id",
                "pluginId",
                "command",
                "args",
                "url",
                "source",
                "repo",
                "repository",
                "installPath",
                "path",
                "serverInfo",
            ):
                if name in value:
                    inspect(value[name], f"{path}.{name}" if path else name)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, f"{path}[{index}]")
        elif isinstance(value, str):
            for match in dict.fromkeys(IDENTITY.findall(value)):
                fields.append({"field": path or "value", "matched_name": match})
            if value in endpoints:
                fields.append(
                    {
                        "field": path or "value",
                        "match": "exact service endpoint from installation settings",
                    }
                )

    if key is not None:
        inspect(key, "registration key")
        if ENVIRONMENT.match(key):
            fields.append({"field": "environment variable", "matched_name": key})
    inspect(value, "")
    return {"entry": "/" + "/".join(location), "category": category, "matched_fields": fields}


def prune(document, endpoints=(), trail=(), removed=None, match_records=None):
    """Remove individual registrations/permissions/hooks, retaining unrelated settings."""
    removed = [] if removed is None else removed
    match_records = [] if match_records is None else match_records
    if isinstance(document, dict):
        registry = bool(trail and str(trail[-1]).lower() in REGISTRIES)
        for key in list(document):
            value = document[key]
            location = (*trail, str(key))
            owned_key = named(str(key)) or str(key).lower().startswith("mcp__") and matches(key)
            owned_env = (
                ENVIRONMENT.match(str(key))
                and trail
                and str(trail[-1]).lower() in {"env", "environment"}
            )
            if owned_key or owned_env or registry and registration_reference(value, endpoints):
                removed.append("/" + "/".join(location))
                match_records.append(entry_match(location, value, endpoints, key=str(key)))
                del document[key]
            else:
                prune(value, endpoints, location, removed, match_records)
    elif isinstance(document, list):
        remove_indices = []
        for index, value in enumerate(document):
            # Nested hook groups must retain unrelated commands in the same group.
            list_kind = str(trail[-1]).lower() if trail else ""
            managed_list = (
                list_kind == "catalog" and any("mcp-server-tools-cache" in part for part in trail)
            ) or list_kind in REGISTRIES | {
                "plugin",
                "allow",
                "deny",
                "ask",
                "hooks",
                "enabledmcpjsonservers",
                "disabledmcpjsonservers",
                "allowedtools",
                "disabledtools",
            }
            direct = managed_list and registration_reference(value, endpoints)
            if direct:
                removed.append("/" + "/".join((*trail, str(index))))
                match_records.append(entry_match((*trail, str(index)), value, endpoints))
                remove_indices.append(index)
            else:
                prune(value, endpoints, (*trail, str(index)), removed, match_records)
        # tomlkit arrays reject slice assignment; preserve untouched items/comments.
        for index in reversed(remove_indices):
            del document[index]
    return removed


@dataclass
class Action:
    kind: str
    target: str
    reason: str
    details: dict = field(default_factory=dict)
    before: str | None = None
    after: str | None = field(default=None, repr=False)

    def public(self):
        # Race/ownership checks stay internal. The report shows actions and match evidence.
        visible = {
            key: value
            for key, value in self.details.items()
            if key
            in {
                "entries",
                "matches",
                "lines",
                "manager",
                "unit",
                "pid",
                "executable",
                "cwd",
                "installer",
                "commands",
                "environment",
                "cleanup_dir",
                "symlink",
            }
        }
        target = self.details.get("resolved", self.target) if self.kind == "edit" else self.target
        return {"kind": self.kind, "target": target, "reason": self.reason, **visible}


class Scanner:
    def __init__(
        self,
        home,
        *,
        scope="all",
        remove_indexes=False,
        remove_runtime_packages=False,
        project_roots=(),
        scan_roots=(),
    ):
        self.home = home.absolute()
        self.uid = home.stat().st_uid
        self.scope = scope
        self.remove_indexes = remove_indexes
        self.remove_runtime_packages = remove_runtime_packages
        self.package_envs = set()
        self.config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        self.data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share"))
        self.cache_home = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
        self.actions = {}
        self.findings = []
        self.scanned = set()
        self.projects = {Path(p).resolve() for p in project_roots}
        self.extra_roots = scan_roots
        self.storage = set()
        self.endpoints = set()
        self.protected = {Path(__file__).resolve().parents[1], Path(sys.prefix).resolve()}
        self.protected.update(
            {
                (self.cache_home / "huggingface").resolve(),
                Path(os.environ.get("HF_HOME", self.cache_home / "huggingface"))
                .expanduser()
                .resolve(),
            }
        )
        self.unit_roots = {}
        self.ancestors = set()
        pid = os.getpid()
        while pid:
            self.ancestors.add(pid)
            item = process_info(Path("/proc") / str(pid))
            pid = item["ppid"] if item else 0

    def protected_path(self, path):
        resolved = path.resolve()
        if source_worktree(resolved):
            return True
        shared = {
            Path("/"),
            self.home.resolve(),
            self.config_home.resolve(),
            self.data_home.resolve(),
            self.cache_home.resolve(),
        }
        if any(resolved == p or resolved in p.parents for p in shared):
            return True
        return any(
            resolved == p or resolved in p.parents or p in resolved.parents for p in self.protected
        )

    def finding(self, path, reason, *, category="review", **details):
        item = {"path": str(path), "reason": reason, "category": category, **details}
        if item not in self.findings:
            self.findings.append(item)

    def add(self, action):
        if action.kind in {"edit", "remove", "package"} and backup_path(action.target):
            return
        self.actions[(action.kind, action.target)] = action

    def delete(self, path, reason):
        path = Path(path).absolute()
        if backup_path(path):
            return
        if not path.exists() and not path.is_symlink():
            return
        if not path.is_symlink():
            guard = self.artifact_guard(path)
            if guard:
                self.finding(
                    path,
                    guard,
                    category="preserved",
                )
                if (
                    guard == "Contains backups; preserve them and remove only eligible siblings"
                    and path.is_dir()
                ):
                    for child in sorted(path.iterdir()):
                        self.delete(child, reason)
                return
        try:
            self.add(
                Action(
                    "remove",
                    str(path),
                    reason,
                    {
                        "identity": fingerprint(path),
                        "resolved_parent": str(path.parent.resolve()),
                        "symlink": path.is_symlink(),
                    },
                )
            )
        except OSError as error:
            self.finding(path, f"Cannot inspect artifact: {error.__class__.__name__}")

    def config(self, path):
        path = Path(path).absolute()
        if path.resolve() in self.scanned or backup_path(path) or not path.is_file():
            return
        self.scanned.add(path.resolve())
        text = ""
        try:
            if path.stat().st_size > MAX_BYTES:
                self.finding(path, "Config exceeds 16 MiB; inspect manually")
                return
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            if not (
                matches(text)
                or any(endpoint in text for endpoint in self.endpoints)
                or '"projects"' in text
                or "[projects." in text
            ):
                return
            if ".toml" in path.name:
                doc = tomlkit.parse(text)
                encode = tomlkit.dumps
            elif any(ext in path.name for ext in (".json", ".code-workspace")):
                try:
                    doc = json.loads(text)
                except ValueError:
                    doc = json5.loads(text)
                encode = lambda value: json.dumps(value, indent=2, ensure_ascii=False) + "\n"
            else:
                if matches(text):
                    self.finding(
                        path, "Reference in unsupported config format; not edited automatically"
                    )
                return
            if not isinstance(doc, (dict, list)):
                return
            if isinstance(doc, dict):
                for project in (
                    doc.get("projects", {}) if isinstance(doc.get("projects"), dict) else ()
                ):
                    if project.startswith("/") and Path(project).is_dir():
                        self.projects.add(Path(project).resolve())
            match_records = []
            removed = prune(doc, self.endpoints, match_records=match_records)
            if removed:
                kinds = list(dict.fromkeys(record["category"] for record in match_records))
                self.add(
                    Action(
                        "edit",
                        str(path),
                        "Remove matched Code Search Local entries: " + ", ".join(kinds),
                        {
                            "entries": removed,
                            "matches": match_records,
                            "resolved": str(path.resolve()),
                            "identity": fingerprint(path),
                        },
                        digest(raw),
                        encode(doc),
                    )
                )
            # Remaining text references are review items, never justification to delete a shared file.
            remaining = encode(doc)
            if matches(remaining):
                locations = list(reference_locations(doc))
                workspace_only = bool(locations) and all(
                    location and location[0] in {"projects", "githubRepoPaths"}
                    for location in locations
                )
                self.finding(
                    path,
                    "Workspace references retained"
                    if workspace_only
                    else "Additional reference outside a recognized registration; inspect manually",
                    category="preserved" if workspace_only else "review",
                    entries=["/" + "/".join(location) for location in locations[:25]],
                )
        except (OSError, ValueError, TypeError) as error:
            if not text or matches(text):
                self.finding(
                    path, f"Cannot parse/read config ({error.__class__.__name__}); not edited"
                )

    def walk_configs(self, base, *, depth=10):
        base = Path(base)
        if not base.is_dir() or backup_path(base):
            return
        for root, dirs, files in os.walk(base, followlinks=False):
            relative = Path(root).relative_to(base)
            dirs[:] = sorted(
                d
                for d in dirs
                if d.casefold() not in {s.casefold() for s in SKIP}
                and not backup_name(d)
                and len(relative.parts) < depth
            )
            for name in sorted(files):
                # Backups are recovery data, never discovery/edit/removal candidates.
                if backup_name(name):
                    continue
                if any(
                    word in name.lower()
                    for word in (
                        "history",
                        "transcript",
                        "auth.json",
                        "credentials",
                        "cookie",
                        "session",
                        "embeddings.json",
                    )
                ):
                    continue
                if not name.endswith((".gz", ".zip", ".zst", ".xz")) and re.search(
                    r"\.(?:jsonc?|toml|yaml|yml|code-workspace)(?:$|[.-])", name
                ):
                    self.config(Path(root) / name)

    def app_state(self):
        aliases = (
            "code-search-local",
            "code_search_local",
            "claude-context-local",
            "claude_context_local",
            "claude-code-search",
            "claude_code_search",
        )
        for alias in aliases:
            for base in (self.home, self.data_home, self.cache_home):
                path = base / (("." + alias) if base == self.home else alias)
                if backup_path(path):
                    continue
                if path.is_dir():
                    self.storage.add(path.resolve())
                if path.is_symlink():
                    self.finding(
                        path,
                        "Storage alias retained so models and retained data stay accessible",
                        category="preserved",
                    )
            root = self.config_home / alias
            if not root.is_dir() or backup_path(root):
                continue
            for name in ("config.json", "settings.json", "installation.json"):
                path = root / name
                if not path.is_file() or backup_path(path):
                    continue
                try:
                    doc = json5.loads(path.read_text())
                    if doc.get("storage"):
                        self.storage.add(Path(doc["storage"]).expanduser().resolve())
                    if doc.get("source"):
                        self.protected.add(Path(doc["source"]).resolve())
                    if "port" in doc:
                        host = doc.get("host", "127.0.0.1")
                        self.endpoints.add(
                            f"http://{('[' + host + ']') if ':' in host else host}:{doc['port']}/mcp"
                        )
                    for target in doc.get("targets", []):
                        for config in target.get("configs", []):
                            self.config(config)
                except (OSError, ValueError, TypeError) as error:
                    self.finding(
                        path, f"Cannot read installation metadata ({error.__class__.__name__})"
                    )
            self.delete(root, "Remove plugin service configuration and installation metadata")
        for name in (
            "CODE_SEARCH_STORAGE",
            "CLAUDE_CONTEXT_LOCAL_STORAGE",
            "CLAUDE_CODE_SEARCH_STORAGE",
        ):
            if os.environ.get(name):
                self.storage.add(Path(os.environ[name]).expanduser().resolve())

    def profiles(self):
        roots = {self.home / name for name in HARNESSES}
        roots.update(self.config_home / name for name in CONFIG_APPS)
        for key in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "OPENCODE_CONFIG_DIR"):
            if os.environ.get(key):
                roots.add(Path(os.environ[key]).expanduser())
        for key in ("OPENCODE_CONFIG",):
            if os.environ.get(key):
                self.config(Path(os.environ[key]).expanduser())
        for path in self.home.glob(".claude.json*"):
            self.config(path)
        for root in sorted(roots):
            if backup_path(root):
                continue
            self.walk_configs(root)
            # Only managed plugin/skill cache locations: never delete the agent application itself.
            for subdir in ("plugins", "skills", "Claude Extensions", "Claude Extensions Settings"):
                managed = root / subdir
                if not managed.is_dir() or backup_path(managed):
                    continue
                for directory, dirs, files in os.walk(managed, followlinks=False):
                    dirs[:] = [
                        name
                        for name in dirs
                        if name not in {"node_modules", ".git"}
                        and not backup_path(Path(directory) / name)
                    ]
                    if "plugin.json" in files and not backup_path(Path(directory) / "plugin.json"):
                        try:
                            manifest = json.loads((Path(directory) / "plugin.json").read_text())
                            if named(str(manifest.get("name", ""))):
                                owner = Path(directory)
                                if owner.name in {".claude-plugin", ".codex-plugin"}:
                                    owner = owner.parent
                                self.delete(
                                    owner, "Remove managed plugin cache identified by its manifest"
                                )
                        except (OSError, ValueError, AttributeError):
                            pass
                    for name in [*dirs, *files]:
                        path = Path(directory) / name
                        if named(name):
                            self.delete(
                                path,
                                "Remove installed plugin, skill or dedicated marketplace cache",
                            )
                            if name in dirs:
                                dirs.remove(name)
        for root in self.extra_roots:
            self.walk_configs(root)
        for root in sorted(self.projects):
            for relative in PROJECT_CONFIGS:
                self.config(root / relative)

    def units(self):
        if self.scope != "system":
            self.unit_roots["user"] = [
                self.home / ".config/systemd/user",
                self.config_home / "systemd/user",
                self.home / ".local/share/systemd/user",
                Path(f"/run/user/{self.uid}/systemd/user"),
                Path(f"/run/user/{self.uid}/systemd/transient"),
            ]
        if self.scope != "user":
            self.unit_roots["system"] = [
                Path(p)
                for p in (
                    "/etc/systemd/system",
                    "/run/systemd/system",
                    "/run/systemd/transient",
                    "/usr/local/lib/systemd/system",
                    "/usr/lib/systemd/system",
                )
            ]
            self.unit_roots.setdefault("user", []).extend(
                Path(p)
                for p in (
                    "/etc/systemd/user",
                    "/usr/local/lib/systemd/user",
                    "/usr/lib/systemd/user",
                )
            )
        for manager, roots in self.unit_roots.items():
            for base in roots:
                if not base.is_dir():
                    continue
                for directory, dirs, files in os.walk(base, followlinks=False):
                    dirs[:] = [d for d in dirs if not backup_path(Path(directory) / d)]
                    for name in files:
                        path = Path(directory) / name
                        if backup_path(path):
                            continue
                        try:
                            content = (
                                path.read_text()
                                if path.is_file() and path.stat().st_size < MAX_BYTES
                                else ""
                            )
                        except (OSError, UnicodeError):
                            continue
                        owned_launch = False
                        for line in content.splitlines():
                            if line.strip().startswith("ExecStart="):
                                try:
                                    owned_launch |= owned_process(
                                        {
                                            "args": shlex.split(
                                                line.partition("=")[2].lstrip("-+!:")
                                            ),
                                            "cwd": str(path.parent),
                                        }
                                    )
                                except ValueError:
                                    pass
                        if matches(content) and not (
                            named(name)
                            or owned_launch
                            or named(path.parent.name.removesuffix(".d"))
                        ):
                            self.finding(path, "Reference in an unrelated unit; inspect manually")
                        if (
                            named(name)
                            or owned_launch
                            or named(path.parent.name.removesuffix(".d"))
                            or path.is_symlink()
                            and named(Path(os.readlink(path)).name)
                        ):
                            unit = name
                            if ".d" in path.parent.suffixes:
                                unit = path.parent.name.removesuffix(".d")
                            if not unit.endswith(
                                (".service", ".socket", ".path", ".timer", ".target", ".scope")
                            ):
                                self.finding(
                                    path, "Reference in a systemd fragment; verify owner manually"
                                )
                                continue
                            # A mixed drop-in for an unrelated service must not stop that service.
                            if path.parent.name.endswith(".d") and not named(unit):
                                self.finding(
                                    path,
                                    "Matching drop-in belongs to an unrelated unit; not stopped automatically",
                                )
                                continue
                            self.add(
                                Action(
                                    "unit",
                                    f"{manager}:{unit}",
                                    "Uninstall matching systemd unit: stop/disable; unit-file removals listed separately",
                                    {"manager": manager, "unit": unit},
                                )
                            )
                            if (
                                str(path).startswith(("/usr/lib/", "/lib/"))
                                and not path.is_symlink()
                            ):
                                self.finding(
                                    path,
                                    "Vendor unit: stop/disable planned; remove its owning OS package manually",
                                )
                            else:
                                self.delete(
                                    path, "Remove matching unit, drop-in or enablement link"
                                )
                            for line in content.splitlines():
                                if line.startswith("WorkingDirectory="):
                                    source = Path(
                                        line.partition("=")[2].strip('"').replace("%%", "%")
                                    )
                                    if source.is_dir() and (source / "pyproject.toml").is_file():
                                        self.protected.add(source.resolve())
                                if line.startswith("ExecStart="):
                                    try:
                                        args = shlex.split(line.partition("=")[2])
                                        if "--storage" in args:
                                            self.storage.add(
                                                Path(args[args.index("--storage") + 1])
                                                .expanduser()
                                                .resolve()
                                            )
                                    except (ValueError, IndexError):
                                        self.finding(
                                            path, "Cannot parse storage option in ExecStart"
                                        )
        # Include loaded transient/deleted units that have no remaining unit file.
        for manager in self.unit_roots:
            if manager == "user" and self.uid != os.getuid():
                self.finding(
                    self.home,
                    "User-manager runtime query skipped for another UID; unit files still scanned",
                )
                continue
            args = [
                "systemctl",
                *(["--user"] if manager == "user" else []),
                "list-units",
                "--all",
                "--no-pager",
                "--output=json",
            ]
            try:
                result = readonly(args)
                if result.returncode:
                    self.finding(manager, "Cannot query systemd manager; unit files still scanned")
                    continue
                for entry in json.loads(result.stdout):
                    name = entry.get("unit", "")
                    if named(name):
                        self.add(
                            Action(
                                "unit",
                                f"{manager}:{name}",
                                "Uninstall matching loaded systemd unit: stop/disable; unit-file removals listed separately",
                                {"manager": manager, "unit": name},
                            )
                        )
            except (OSError, ValueError, subprocess.SubprocessError):
                self.finding(
                    manager, "Systemd runtime inventory unavailable; unit files still scanned"
                )

    def processes(self, proc=Path("/proc")):
        inventory = {}
        for path in proc.iterdir():
            if path.name.isdigit():
                info = process_info(path)
                if (
                    info
                    and info["state"] not in {"Z", "X"}
                    and info["uid"] == self.uid
                    and info["pid"] not in self.ancestors
                ):
                    inventory[info["pid"]] = info
        owned = {pid for pid, info in inventory.items() if owned_process(info)}
        while True:
            children = {pid for pid, info in inventory.items() if info["ppid"] in owned}
            if children <= owned:
                break
            owned.update(children)
        for pid in sorted(owned):
            info = inventory[pid]
            cwd = Path(info["cwd"])
            if matches(str(cwd)) and ((cwd / "pyproject.toml").exists() or (cwd / ".git").exists()):
                self.protected.add(cwd.resolve())
            self.add(
                Action(
                    "process",
                    str(pid),
                    "Stop matching server/launcher or its descendant",
                    {
                        "pid": pid,
                        "start_ticks": info["start_ticks"],
                        "uid": info["uid"],
                        "executable": info["args"][0] if info["args"] else "",
                        "cwd": info["cwd"],
                    },
                )
            )

    def artifact_guard(self, path, *, environment=False):
        """A package manager must obey the same source/model protections as file removal."""
        path = Path(path)
        if backup_path(path):
            return "Backup path is protected"
        if self.protected_path(path):
            return "Source worktree, cleanup interpreter, model storage or shared directory is protected"
        if (
            path.name.endswith((".safetensors", ".gguf", ".ggml"))
            or path.name == "pytorch_model.bin"
        ):
            return "Downloaded models are always preserved"
        for root, dirs, files in os.walk(path, followlinks=False):
            if any(
                (Path(root) / name).is_symlink() and source_worktree(Path(root) / name)
                for name in dirs
            ):
                return "Contains a link into a source worktree"
            if ".git" in dirs or ".git" in files:
                return "Contains a source clone/worktree"
            if any(name.startswith("models--") for name in dirs) or any(
                name.endswith((".safetensors", ".gguf", ".ggml")) or name == "pytorch_model.bin"
                for name in files
            ):
                return "Contains downloaded models, which are always preserved"
            if not environment and "pyvenv.cfg" in files:
                return "Contains a runtime environment; only its original installer may remove it"
            if any(
                backup_name(name)
                or (Path(root) / name).is_symlink()
                and backup_path(Path(root) / name)
                for name in (*dirs, *files)
            ):
                return "Contains backups; preserve them and remove only eligible siblings"
        return None

    def package_action(self, target, commands, installer, evidence, *, env=None, cleanup_dir=None):
        target = Path(target).absolute()
        if backup_path(target):
            return
        if not self.remove_runtime_packages:
            self.finding(
                target,
                "Runtime/package retained; requires --remove-runtime-packages",
                category="preserved",
            )
            return
        for path in (target, Path(cleanup_dir) if cleanup_dir else target):
            reason = self.artifact_guard(path, environment=True)
            if reason:
                self.finding(path, reason, category="preserved")
                return
        if any(not command or not command[0] for command in commands):
            self.finding(target, "Original installer is unavailable; package/environment retained")
            return
        details = {
            "installer": installer,
            "commands": commands,
            "environment": env or {},
            "identity": fingerprint(target),
            "resolved": str(target.resolve()),
            "evidence": {str(p): digest(p.read_bytes()) for p in evidence},
        }
        if cleanup_dir:
            details.update(
                cleanup_dir=str(cleanup_dir), cleanup_identity=fingerprint(Path(cleanup_dir))
            )
        self.add(
            Action(
                "package",
                str(target),
                "Uninstall with recorded installer (--remove-runtime-packages)",
                details,
            )
        )

    def python_environment(self, venv, *, managed_root=None):
        venv = Path(venv).absolute()
        if backup_path(venv) or venv.resolve() in self.package_envs:
            return
        self.package_envs.add(venv.resolve())
        metadata = sorted(venv.glob("lib/python*/site-packages/*.dist-info"))
        selected = metadata if managed_root else [p for p in metadata if named(p.name)]
        if not selected:
            return
        if not self.remove_runtime_packages:
            self.finding(
                venv,
                "Runtime/package retained; requires --remove-runtime-packages",
                category="preserved",
            )
            return
        if self.artifact_guard(venv, environment=True):
            self.finding(venv, self.artifact_guard(venv, environment=True), category="preserved")
            return
        python = venv / "bin/python"
        if not python.is_file() or not (venv / "pyvenv.cfg").is_file():
            self.finding(
                venv, "Missing venv interpreter/marker; no installer command can be selected"
            )
            return
        groups, evidence = {}, [venv / "pyvenv.cfg"]
        for entry in selected:
            receipt = entry / "INSTALLER"
            owner = receipt.read_text().strip() if receipt.is_file() else ""
            if owner not in {"pip", "uv"}:
                self.finding(entry, "Unknown/missing INSTALLER metadata; environment retained")
                return
            groups.setdefault(owner, []).append(distribution_name(entry))
            evidence.append(receipt)
        commands = []
        for owner, packages in sorted(groups.items()):
            if owner == "uv":
                commands.append(
                    [
                        manager_executable("uv"),
                        "pip",
                        "uninstall",
                        "--python",
                        str(python),
                        *packages,
                    ]
                )
            else:
                if not list(venv.glob("lib/python*/site-packages/pip/__main__.py")):
                    self.finding(
                        venv,
                        "pip installed this distribution but is unavailable in this environment; retained",
                    )
                    return
                commands.append([str(python), "-m", "pip", "uninstall", "-y", *packages])
        # Only our dedicated generated runtime may lose its whole environment after uninstall.
        if managed_root:
            evidence.extend([managed_root / "README.md", managed_root / "uv.lock"])
        self.package_action(
            venv, commands, "+".join(sorted(groups)), evidence, cleanup_dir=managed_root
        )

    def installations(self):
        tool_roots = {
            self.data_home / "uv/tools": "uv",
            self.data_home / "pipx/venvs": "pipx",
            self.home / ".local/pipx/venvs": "pipx",
        }
        if os.environ.get("UV_TOOL_DIR"):
            tool_roots[Path(os.environ["UV_TOOL_DIR"])] = "uv"
        if os.environ.get("PIPX_HOME"):
            tool_roots[Path(os.environ["PIPX_HOME"]) / "venvs"] = "pipx"
        for root, installer in tool_roots.items():
            if not root.is_dir() or backup_path(root):
                continue
            for venv in sorted(root.iterdir()):
                if not venv.is_dir() or backup_path(venv):
                    continue
                self.package_envs.add(venv.resolve())
                receipt = venv / ("uv-receipt.toml" if installer == "uv" else "pipx_metadata.json")
                if backup_path(receipt):
                    continue
                try:
                    doc = (
                        tomlkit.parse(receipt.read_text())
                        if installer == "uv"
                        else json.loads(receipt.read_text())
                    )
                    if installer == "uv":
                        packages = [
                            r["name"]
                            for r in doc.get("tool", {}).get("requirements", [])
                            if named(r.get("name", ""))
                        ]
                        if not packages:
                            continue
                        commands = [[manager_executable("uv"), "tool", "uninstall", *packages]]
                        env = {"UV_TOOL_DIR": str(root)}
                    else:
                        package = doc.get("main_package", {}).get("package", "")
                        if named(package):
                            commands = [[manager_executable("pipx"), "uninstall", venv.name]]
                        else:
                            injected = [p for p in doc.get("injected_packages", {}) if named(p)]
                            if not injected:
                                continue
                            commands = [
                                [manager_executable("pipx"), "uninject", venv.name, *injected]
                            ]
                        env = {"PIPX_HOME": str(root.parent)}
                    self.package_action(venv, commands, installer, [receipt], env=env)
                except (OSError, ValueError, TypeError, KeyError):
                    if named(venv.name):
                        self.finding(
                            venv,
                            "Installer receipt missing/malformed; environment retained",
                            category="review" if self.remove_runtime_packages else "preserved",
                        )
        # Find console entry points without deleting them behind their installer's back.
        bins = {self.home / ".local/bin", self.home / "bin", self.home / ".dot/bin"}
        bins.update(Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p)
        for key in ("UV_TOOL_BIN_DIR", "PIPX_BIN_DIR"):
            if os.environ.get(key):
                bins.add(Path(os.environ[key]))
        for root in sorted(bins):
            if (
                backup_path(root)
                or not root.is_dir()
                or self.scope == "user"
                and not os.access(root, os.W_OK)
            ):
                continue
            for path in root.iterdir():
                if not named(path.name) or backup_path(path):
                    continue
                owner = path.resolve().parent.parent
                if not (owner / "pyvenv.cfg").is_file():
                    try:
                        header = path.open("rb").readline(4096).decode().strip()
                        if header.startswith("#!"):
                            owner = Path(shlex.split(header[2:])[0]).parent.parent
                    except (OSError, UnicodeError, ValueError, IndexError):
                        pass
                if (owner / "pyvenv.cfg").is_file():
                    self.python_environment(owner)
                else:
                    self.finding(
                        path,
                        "Launcher retained; original installer ownership is unknown",
                        category="review" if self.remove_runtime_packages else "preserved",
                    )
        env_roots = [self.home / ".venvs", self.home / ".virtualenvs"]
        for project in self.projects:
            env_roots.extend([project / ".venv", project / ".venvs"])
        for root in env_roots:
            if root.is_dir() and not backup_path(root):
                if (root / "pyvenv.cfg").is_file():
                    self.python_environment(root)
                for candidate in root.iterdir():
                    if candidate.is_dir() and (candidate / "pyvenv.cfg").is_file():
                        self.python_environment(candidate)
        for root in sorted(self.storage):
            runtimes = root / "runtimes"
            if not runtimes.is_dir() or backup_path(runtimes):
                continue
            for runtime in sorted(runtimes.iterdir()):
                if backup_path(runtime):
                    continue
                marker = runtime / "README.md"
                if backup_path(marker) or backup_path(runtime / "uv.lock"):
                    continue
                if (
                    marker.is_file()
                    and marker.read_text().strip() == "Managed code-search-local runtime."
                    and (runtime / "uv.lock").is_file()
                ):
                    self.python_environment(runtime / ".venv", managed_root=runtime)
                else:
                    self.finding(
                        runtime,
                        "Unrecognized runtime provenance; environment retained",
                        category="review" if self.remove_runtime_packages else "preserved",
                    )
        # uvx environments and package caches are owned by uv. Never rmtree cache internals.
        uv_cache = Path(os.environ.get("UV_CACHE_DIR", self.cache_home / "uv"))
        if uv_cache.is_dir() and not backup_path(uv_cache):
            packages = set()
            for directory, dirs, _ in os.walk(uv_cache, followlinks=False):
                depth = len(Path(directory).relative_to(uv_cache).parts)
                dirs[:] = [d for d in dirs if not backup_name(d) and depth < 9]
                for name in dirs:
                    if name.endswith(".dist-info") and named(name):
                        packages.add(distribution_name(Path(name)))
            if packages:
                self.package_action(
                    uv_cache,
                    [[manager_executable("uv"), "cache", "clean", *sorted(packages)]],
                    "uvx/uv-cache",
                    [],
                    env={"UV_CACHE_DIR": str(uv_cache)},
                )
        # Other installer families are inventoried; this option never guesses their ownership.
        for site in self.home.glob(".local/lib/python*/site-packages"):
            for metadata in site.glob("*.dist-info"):
                if named(metadata.name):
                    self.finding(
                        metadata,
                        "Outside a venv; inspect original installer/OS ownership manually",
                        category="review" if self.remove_runtime_packages else "preserved",
                    )
        npm_roots = [
            self.home / ".local/lib/node_modules",
            self.config_home / "opencode/node_modules",
            self.home / ".bun/install/global/node_modules",
        ]
        npm_roots += list((self.home / ".npm/_npx").glob("*/node_modules"))
        npm_roots += list((self.home / ".nvm/versions/node").glob("*/lib/node_modules"))
        if self.scope != "user":
            npm_roots.extend([Path("/usr/local/lib/node_modules"), Path("/usr/lib/node_modules")])
        for root in npm_roots:
            for package in root.glob("*"):
                if named(package.name):
                    self.finding(
                        package,
                        "Non-Python installer package retained; remove with its original package manager",
                        category="review" if self.remove_runtime_packages else "preserved",
                    )

    def launch_references(self):
        for root in (self.config_home / "autostart", self.data_home / "applications"):
            if root.is_dir():
                for path in root.glob("*.desktop"):
                    if backup_path(path):
                        continue
                    try:
                        content = path.read_text()
                        launches = [
                            line.partition("=")[2]
                            for line in content.splitlines()
                            if line.startswith("Exec=")
                        ]
                        if named(path.stem) or any(
                            owned_process({"args": shlex.split(command), "cwd": str(root)})
                            for command in launches
                        ):
                            self.delete(path, "Remove desktop/autostart launcher for matching tool")
                        elif matches(content):
                            self.finding(
                                path, "Reference in an unrelated desktop entry; inspect manually"
                            )
                    except (OSError, UnicodeError, ValueError):
                        self.finding(path, "Cannot read/parse desktop entry")
        startup = [
            self.home / name
            for name in (
                ".bashrc",
                ".bash_profile",
                ".profile",
                ".zshrc",
                ".zprofile",
                ".pam_environment",
            )
        ]
        startup += list((self.config_home / "environment.d").glob("*.conf"))
        startup += list((self.config_home / "fish/conf.d").glob("*.fish"))
        for path in startup:
            if not path.is_file() or backup_path(path):
                continue
            try:
                raw = path.read_bytes()
                lines = raw.decode().splitlines(keepends=True)
                removed, retained = [], []
                for number, line in enumerate(lines, 1):
                    stripped = line.strip()
                    env_line = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)=", stripped)
                    own_alias = re.match(r"alias\s+([\w-]+)=", stripped)
                    simple = bool(
                        env_line
                        and ENVIRONMENT.match(env_line[1])
                        or own_alias
                        and named(own_alias[1])
                    )
                    if (
                        simple
                        and not stripped.endswith("\\")
                        and not any(c in stripped for c in (";", "&&", "||", "$(", "`"))
                    ):
                        removed.append(number)
                    else:
                        retained.append(line)
                        if matches(line) and not stripped.startswith("#"):
                            self.finding(
                                f"{path}:{number}",
                                "Reference in compound shell code; review manually",
                            )
                if removed:
                    self.add(
                        Action(
                            "edit",
                            str(path),
                            "Remove standalone matching shell aliases/environment assignments",
                            {
                                "lines": removed,
                                "resolved": str(path.resolve()),
                                "identity": fingerprint(path),
                            },
                            digest(raw),
                            "".join(retained),
                        )
                    )
            except (OSError, UnicodeError):
                self.finding(path, "Cannot read shell/environment configuration")

    def cron(self):
        """Read crontabs without installing a replacement during discovery."""
        if self.scope != "system":
            try:
                command = [
                    "crontab",
                    *(["-u", pwd.getpwuid(self.uid).pw_name] if self.uid != os.getuid() else []),
                    "-l",
                ]
                result = readonly(command)
                if result.returncode == 0:
                    after, removed, ambiguous = clean_cron(result.stdout, self.home)
                    if removed:
                        self.add(
                            Action(
                                "crontab",
                                str(self.uid),
                                "Remove matching user cron launches",
                                {"uid": self.uid, "lines": removed},
                                digest(result.stdout.encode()),
                                after,
                            )
                        )
                    if ambiguous:
                        self.finding(
                            f"crontab:{self.uid}",
                            f"Compound/ambiguous entries require review at lines {ambiguous}",
                        )
                elif "no crontab" not in result.stderr.lower():
                    self.finding(f"crontab:{self.uid}", "Unable to inspect user crontab")
            except FileNotFoundError:
                pass  # Cron is not installed.
            except (OSError, subprocess.SubprocessError):
                self.finding(f"crontab:{self.uid}", "Unable to inspect user crontab")
        if self.scope != "user":
            paths = [Path("/etc/crontab"), *Path("/etc/cron.d").glob("*")]
            for path in paths:
                if not path.is_file() or backup_path(path):
                    continue
                try:
                    raw = path.read_bytes()
                    after, removed, ambiguous = clean_cron(raw.decode(), self.home, system=True)
                    if removed:
                        self.add(
                            Action(
                                "edit",
                                str(path),
                                "Remove matching system cron launches",
                                {
                                    "lines": removed,
                                    "resolved": str(path.resolve()),
                                    "identity": fingerprint(path),
                                },
                                digest(raw),
                                after,
                            )
                        )
                    if ambiguous:
                        self.finding(
                            path,
                            f"Compound/ambiguous cron entries require review at lines {ambiguous}",
                        )
                except (OSError, UnicodeError):
                    self.finding(path, "Unable to inspect system crontab")

    def finish(self):
        for root in sorted(self.storage):
            self.protected.add((root / "models").resolve())
            self.finding(
                root / "models",
                "Downloaded models always retained, including with --remove-all",
                category="preserved",
            )
            if not any(
                (root / marker).exists()
                for marker in (
                    "state.sqlite3",
                    "embedding-cache.sqlite3",
                    "runtimes",
                    "models",
                    "merkle",
                    "projects",
                    "indexes",
                )
            ):
                self.finding(root, "Storage path lacks recognized data markers; inspect manually")
                continue
            # Enumerate index artifacts individually. Never remove their storage parent/models.
            indexes = [root / name for name in ("projects", "indexes", "merkle")]
            for name in ("state.sqlite3", "embedding-cache.sqlite3"):
                indexes.extend(
                    root / (name + suffix) for suffix in ("", "-wal", "-shm", "-journal")
                )
            for path in indexes:
                if self.remove_indexes:
                    self.delete(
                        path,
                        "Remove project index, embedding cache or index statistics (--remove-indexes)",
                    )
                elif path.exists():
                    self.finding(
                        path, "Index retained; requires --remove-indexes", category="preserved"
                    )
        # Source roots discovered from later unit/installation records also protect earlier candidates.
        for key, action in list(self.actions.items()):
            if (
                action.kind == "remove"
                and not action.details["symlink"]
                and self.protected_path(Path(action.target))
            ):
                self.finding(
                    action.target,
                    "Protected source/shared directory; removal excluded",
                    category="preserved",
                )
                del self.actions[key]
        # A parent removal already handles children and config edits inside it.
        removals = [
            Path(a.target)
            for a in self.actions.values()
            if a.kind == "remove" and not a.details["symlink"]
        ]
        actions = [
            a
            for a in self.actions.values()
            if a.kind not in {"remove", "edit", "package"}
            or not any(p in Path(a.target).parents for p in removals)
        ]
        order = {"unit": 0, "edit": 1, "crontab": 1, "process": 2, "package": 3, "remove": 4}
        actions.sort(
            key=lambda a: (
                bool(a.details.get("matches"))
                and all(
                    match["category"] in {"cached MCP discovery entry", "marketplace catalog entry"}
                    for match in a.details["matches"]
                ),
                order[a.kind],
                0 if a.target.endswith((".path", ".timer", ".socket")) else 1,
                a.target,
            )
        )
        return actions

    def scan(self):
        self.app_state()
        self.units()
        for root in self.storage:
            self.protected.add((root / "models").resolve())
        self.profiles()
        self.processes()
        self.installations()
        self.launch_references()
        self.cron()
        return self.finish()


def clean_cron(content, home, *, system=False):
    kept, removed, ambiguous = [], [], []
    for number, line in enumerate(content.splitlines(keepends=True), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not matches(line):
            kept.append(line)
            continue
        fields = stripped.split(None, (1 if stripped.startswith("@") else 5) + int(system))
        command = fields[-1]
        try:
            owned = not any(
                char in command for char in (";", "|", "&", "$(", "`", "\\", "%")
            ) and owned_process({"args": shlex.split(command), "cwd": str(home)})
        except ValueError:
            owned = False
        if owned and len(fields) > 1:
            removed.append(number)
        else:
            kept.append(line)
            ambiguous.append(number)
    return "".join(kept), removed, ambiguous


def process_info(path):
    try:
        text = (path / "stat").read_text()
        fields = text[text.rfind(")") + 2 :].split()
        return {
            "pid": int(path.name),
            "ppid": int(fields[1]),
            "state": fields[0],
            "start_ticks": fields[19],
            "uid": path.stat().st_uid,
            "args": [
                part.decode(errors="replace")
                for part in (path / "cmdline").read_bytes().split(b"\0")
                if part
            ],
            "cwd": str((path / "cwd").resolve()),
        }
    except (OSError, ValueError, IndexError):
        return None


def owned_process(info):
    args = info["args"]
    if not args or any("clean-existing-installations-and-configs.py" in arg for arg in args):
        return False
    executable = Path(args[0]).name
    if named(executable):
        return True
    # Parse launch positions: prompts, `python -c`, pytest arguments and uv project paths
    # mentioning this repository must never identify an unrelated process as our server.
    remaining = args[1:]
    cwd = info["cwd"]
    if executable == "uv":
        if "run" not in remaining:
            return False
        remaining = remaining[remaining.index("run") + 1 :]
    if executable in {"uv", "uvx"}:
        while remaining and remaining[0].startswith("-"):
            option = remaining.pop(0)
            if option in {
                "--directory",
                "--project",
                "--from",
                "--with",
                "--with-editable",
                "--python",
                "--index",
                "--index-url",
                "--extra-index-url",
            }:
                if not remaining:
                    return False
                value = remaining.pop(0)
                if option in {"--directory", "--project"}:
                    cwd = value
        return bool(remaining) and owned_process({"args": remaining, "cwd": cwd})
    if executable.startswith("python"):
        while remaining and remaining[0].startswith("-"):
            option = remaining.pop(0)
            if option == "-m":
                return bool(remaining and named(remaining[0]))
            if option not in {"-u", "-I", "-E", "-s", "-S", "-B", "-P"}:
                return False
        if not remaining:
            return False
        script = remaining[0]
        if named(Path(script).name):
            return True
        return script.endswith(
            (
                "mcp_server/server.py",
                "claude_context_local/server.py",
                "code_search_local/server.py",
            )
        ) and (matches(cwd) or matches(script))
    if executable in {"node", "bun"} and remaining:
        script = remaining[0]
        return (
            not script.startswith("-")
            and script.endswith((".js", ".mjs", ".cjs"))
            and matches(script)
        )
    return False


def unchanged(action):
    if action.kind in {"remove", "edit"}:
        path = Path(action.target)
        if not path.exists() and not path.is_symlink():
            return action.kind == "remove"
        if fingerprint(path) != action.details["identity"]:
            return False
        if action.kind == "edit":
            return (
                str(path.resolve()) == action.details["resolved"]
                and digest(path.read_bytes()) == action.before
            )
        return str(path.parent.resolve()) == action.details["resolved_parent"]
    if action.kind == "package":
        path = Path(action.target)
        return (
            path.exists()
            and fingerprint(path) == action.details["identity"]
            and str(path.resolve()) == action.details["resolved"]
            and all(
                Path(p).is_file() and digest(Path(p).read_bytes()) == expected
                for p, expected in action.details["evidence"].items()
            )
        )
    return True


def systemctl(manager, scanner):
    if manager == "system":
        return ["systemctl"]
    if os.getuid() == scanner.uid:
        return ["systemctl", "--user"]
    user = pwd.getpwuid(scanner.uid).pw_name
    return [
        "runuser",
        "-u",
        user,
        "--",
        "env",
        f"XDG_RUNTIME_DIR=/run/user/{scanner.uid}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{scanner.uid}/bus",
        "systemctl",
        "--user",
    ]


def atomic_write(path, data, mode):
    fd, temporary = tempfile.mkstemp(prefix=".cleanup-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def apply_plan(scanner, actions, backup, grace):
    """DESTRUCTIVE: called only after explicit --apply --reviewed and typed confirmation.

    This function has intentionally NOT been executed during implementation, even in tests.
    """
    for action in actions:
        if action.kind in {"edit", "remove", "package"} and backup_path(action.target):
            raise click.ClickException(f"Backup path is protected: {action.target}")
        if not unchanged(action):
            raise click.ClickException(f"Changed since discovery; rerun dry-run: {action.target}")
        if action.kind == "package" and scanner.artifact_guard(
            Path(action.target), environment=True
        ):
            raise click.ClickException(f"Protected runtime cannot be uninstalled: {action.target}")
        if (
            action.kind == "package"
            and action.details.get("cleanup_dir")
            and scanner.artifact_guard(Path(action.details["cleanup_dir"]), environment=True)
        ):
            raise click.ClickException(
                f"Protected runtime directory: {action.details['cleanup_dir']}"
            )
        if (
            action.kind == "remove"
            and not Path(action.target).is_symlink()
            and scanner.artifact_guard(Path(action.target))
        ):
            raise click.ClickException(f"Artifact now contains protected data: {action.target}")
        if action.kind == "unit" and action.details["manager"] == "system" and os.geteuid() != 0:
            raise click.ClickException(
                "System units require root. Review user-only --scope user or rerun as root with --home explicitly set."
            )
        if action.kind in {"edit", "remove"} and not os.access(Path(action.target).parent, os.W_OK):
            raise click.ClickException(f"Insufficient write permission: {action.target}")
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    # Archive modified config files privately, outside all scanned harness locations.
    for index, action in enumerate(actions):
        if action.kind == "edit":
            source = Path(action.target).resolve()
            atomic_write(backup / f"{index:04d}-{source.name}", source.read_bytes(), 0o600)
    atomic_write(
        backup / "manifest.json",
        json.dumps([a.public() for a in actions], indent=2).encode(),
        0o600,
    )
    units = [a for a in actions if a.kind == "unit"]
    for action in units:
        command = systemctl(action.details["manager"], scanner)
        # Stop activation first; static/transient units do not support enable/disable.
        state = readonly([*command, "is-enabled", action.details["unit"]]).stdout.strip()
        if state in {"enabled", "enabled-runtime", "linked", "linked-runtime", "alias"}:
            subprocess.run([*command, "disable", action.details["unit"]], check=True)
        subprocess.run([*command, "stop", "--no-block", action.details["unit"]], check=True)
    for action in actions:
        if action.kind == "edit":
            if backup_path(action.target) or not unchanged(action):
                raise click.ClickException(
                    f"Config changed during cleanup; saved backup: {action.target}"
                )
            path = Path(action.target).resolve()
            info = path.stat()
            atomic_write(path, action.after.encode(), stat.S_IMODE(info.st_mode) & 0o600)
            if os.geteuid() == 0:
                os.chown(path, info.st_uid, info.st_gid)
        elif action.kind == "crontab":
            command = [
                "crontab",
                *(["-u", pwd.getpwuid(scanner.uid).pw_name] if scanner.uid != os.getuid() else []),
            ]
            current = readonly([*command, "-l"])
            if current.returncode or digest(current.stdout.encode()) != action.before:
                raise click.ClickException("Crontab changed since discovery; refusing replacement")
            atomic_write(backup / "crontab.txt", current.stdout.encode(), 0o600)
            subprocess.run([*command, "-"], input=action.after, text=True, check=True)
    processes = [a for a in actions if a.kind == "process"]

    def alive(action):
        current = process_info(Path("/proc") / action.target)
        return (
            current
            and current["state"] not in {"Z", "X"}
            and current["uid"] == action.details["uid"]
            and current["start_ticks"] == action.details["start_ticks"]
        )

    for sig in (signal.SIGTERM, signal.SIGKILL):
        for action in processes:
            if alive(action):
                try:
                    os.kill(action.details["pid"], sig)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + (grace if sig == signal.SIGTERM else 3)
        while any(alive(a) for a in processes) and time.monotonic() < deadline:
            time.sleep(0.1)
    if any(alive(a) for a in processes):
        raise click.ClickException("Some server processes remain; refusing to delete installations")
    scanner.processes()
    if any(alive(action) for action in scanner.actions.values() if action.kind == "process"):
        raise click.ClickException(
            "A harness restarted a server; close the harness and rerun the dry-run before cleanup"
        )
    for action in units:
        result = readonly(
            [*systemctl(action.details["manager"], scanner), "is-active", action.details["unit"]]
        )
        if result.stdout.strip() in {"active", "activating", "deactivating", "reloading"}:
            raise click.ClickException(f"Unit has not stopped: {action.target}; files retained")
    for action in actions:
        if action.kind == "package":
            if not unchanged(action) or scanner.artifact_guard(
                Path(action.target), environment=True
            ):
                raise click.ClickException(f"Runtime ownership/protection changed: {action.target}")
            if action.details.get("cleanup_dir") and scanner.artifact_guard(
                Path(action.details["cleanup_dir"]), environment=True
            ):
                raise click.ClickException(
                    f"Runtime directory now contains protected data: {action.details['cleanup_dir']}"
                )
            for command in action.details["commands"]:
                overrides = {"HOME": str(scanner.home), **action.details["environment"]}
                if scanner.uid != os.getuid():
                    command = [
                        "runuser",
                        "-u",
                        pwd.getpwuid(scanner.uid).pw_name,
                        "--",
                        "env",
                        *[f"{key}={value}" for key, value in overrides.items()],
                        *command,
                    ]
                subprocess.run(
                    command, env={**os.environ, **overrides}, check=True, cwd=scanner.home
                )
            if action.details.get("cleanup_dir"):
                # Shared venvs stay. A verified generated runtime loses its empty package environment
                # and provisioning metadata only after every original-installer uninstall succeeded.
                path = Path(action.details["cleanup_dir"])
                if fingerprint(path) != action.details[
                    "cleanup_identity"
                ] or scanner.artifact_guard(path, environment=True):
                    raise click.ClickException(
                        f"Managed runtime changed/protected; directory retained: {path}"
                    )
                shutil.rmtree(path)
        elif action.kind == "remove":
            path = Path(action.target)
            if (
                backup_path(path)
                or not unchanged(action)
                or not path.is_symlink()
                and scanner.artifact_guard(path)
            ):
                raise click.ClickException(f"Artifact changed; refusing removal: {path}")
            if path.is_symlink() or path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path)
    for manager in {a.details["manager"] for a in units}:
        subprocess.run([*systemctl(manager, scanner), "daemon-reload"], check=True)
    click.echo(f"Cleanup applied. Private configuration backups: {backup}")
    if any(item["category"] == "review" for item in scanner.findings):
        raise click.ClickException(
            "Known installations removed; reported references still require manual review"
        )


@click.command(context_settings={"max_content_width": 100})
@click.option(
    "--dry-run",
    is_flag=True,
    help="Read-only discovery and report. Creates no backups and changes nothing.",
)
@click.option(
    "--apply",
    is_flag=True,
    help="Perform cleanup only after you have personally reviewed this script.",
)
@click.option(
    "--reviewed",
    is_flag=True,
    help="Required with --apply; acknowledges personal review of the script.",
)
@click.option(
    "--home",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=lambda: str(Path.home()),
    show_default="current user's home",
)
@click.option(
    "--scope",
    type=click.Choice(["user", "system", "all"]),
    default="all",
    show_default=True,
    help="Which systemd/launcher scopes to inventory. Harnesses belong to --home.",
)
@click.option(
    "--project-root",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Additional workspace with project-local agent configs; repeat as needed.",
)
@click.option(
    "--scan-root",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Additional directory of harness configurations to scan recursively.",
)
@click.option(
    "--remove-indexes",
    is_flag=True,
    help="Remove project indexes, embedding caches and index statistics. Always retain models.",
)
@click.option(
    "--remove-runtime-packages",
    is_flag=True,
    help="Uninstall runtime/CLI packages with their original installer; never source-worktree environments.",
)
@click.option(
    "--remove-all",
    is_flag=True,
    help="Enable --remove-indexes and --remove-runtime-packages. Models and source environments are still preserved.",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit the redacted dry-run inventory as JSON."
)
@click.option(
    "--backup-dir",
    type=click.Path(path_type=Path),
    help="New private backup directory for --apply; never written during --dry-run.",
)
@click.option(
    "--grace-seconds",
    type=click.IntRange(1, 60),
    default=10,
    show_default=True,
    help="SIGTERM grace period before SIGKILL during --apply.",
)
def main(
    dry_run,
    apply,
    reviewed,
    home,
    scope,
    project_root,
    scan_root,
    remove_indexes,
    remove_runtime_packages,
    remove_all,
    as_json,
    backup_dir,
    grace_seconds,
):
    """Find current/legacy plugin registrations, services, processes and installations.

    Default cleanup uninstalls systemd services (stop, disable and remove unit
    files) and removes this plugin's MCP/plugin registrations from all discovered
    harnesses. Only index and runtime/package removal require optional flags.

    Start with --dry-run. No action is taken without --apply --reviewed followed by
    an interactive confirmation. Source checkouts, backups, agent applications and
    conversation history are preserved. Unknown/mixed references are reported.
    """
    if dry_run == apply:
        raise click.UsageError(
            "Specify exactly one of --dry-run or --apply; cleanup is never implicit"
        )
    if apply and (not reviewed or as_json):
        raise click.UsageError("--apply requires --reviewed and an interactive report (no --json)")
    if sys.platform != "linux":
        raise click.ClickException("This cleanup script supports Linux systemd installations")
    if os.geteuid() == 0 and os.environ.get("SUDO_USER") and home == Path.home():
        raise click.UsageError("When using sudo, specify the original user's --home explicitly")
    remove_indexes = remove_indexes or remove_all
    remove_runtime_packages = remove_runtime_packages or remove_all
    scanner = Scanner(
        home,
        scope=scope,
        remove_indexes=remove_indexes,
        remove_runtime_packages=remove_runtime_packages,
        project_roots=project_root,
        scan_roots=scan_root,
    )
    actions = scanner.scan()
    report = {
        "dry_run": dry_run,
        "home": str(home),
        "scope": scope,
        "remove_indexes": remove_indexes,
        "remove_runtime_packages": remove_runtime_packages,
        "remove_all": remove_all,
        "models_preserved": True,
        "counts": dict(Counter(a.kind for a in actions)),
        "actions": [a.public() for a in actions],
        "findings": scanner.findings,
        "config_files_examined": len(scanner.scanned),
    }
    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        click.echo("DRY RUN — no changes" if dry_run else "REVIEWED CLEANUP PLAN")
        click.echo(f"Planned actions: {len(actions)}; counts: {report['counts']}")
        for action in actions:
            public = action.public()
            click.echo(f"{action.kind.upper():8} {public['target']}\n         {action.reason}")
            for command in public.get("commands", []):
                click.echo(f"         command: {shlex.join(command)}")
            for match in public.get("matches", []):
                fields = "; ".join(
                    f"{field['field']}: {field.get('matched_name', field.get('match'))}"
                    for field in match["matched_fields"]
                )
                click.echo(f"         {match['entry']} ({fields})")
            if not public.get("matches"):
                for entry in public.get("entries", []):
                    click.echo(f"         entry: {entry}")
            if public.get("lines"):
                click.echo(f"         lines: {', '.join(map(str, public['lines']))}")
        for item in scanner.findings:
            click.echo(f"{item['category'].upper():8} {item['path']}\n         {item['reason']}")
    if dry_run:
        return
    if not sys.stdin.isatty():
        raise click.ClickException("Real cleanup requires interactive personal confirmation")
    answer = click.prompt("After reviewing the script and plan, type REMOVE BOTH INSTALLATIONS")
    if answer != "REMOVE BOTH INSTALLATIONS":
        raise click.ClickException("Confirmation did not match; no changes made")
    backup = backup_dir or home / ".local/state/mcp-cleanup-backups" / time.strftime(
        "%Y%m%d-%H%M%S"
    )
    if any(
        Path(a.target) == backup or Path(a.target) in backup.parents
        for a in actions
        if a.kind == "remove"
    ):
        raise click.ClickException("Backup directory cannot be inside a removal target")
    apply_plan(scanner, actions, backup, grace_seconds)


if __name__ == "__main__":
    main()
