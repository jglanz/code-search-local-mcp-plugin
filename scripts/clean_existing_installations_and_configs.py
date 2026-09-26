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

# Cleanup owns these contracts independently of a possibly broken installation.
APPLICATION_NAME = "code-search-local"
COMMAND_DAEMON_RELOAD = "daemon-reload"
COMMAND_DISABLE = "disable"
COMMAND_PIP = "pip"
COMMAND_STOP = "stop"
COMMAND_SYSTEMCTL = "systemctl"
COMMAND_UNINSTALL = "uninstall"
ENV_CLAUDE_CODE_SEARCH_STORAGE = "CLAUDE_CODE_SEARCH_STORAGE"
ENV_CLAUDE_CONFIG_DIR = "CLAUDE_CONFIG_DIR"
ENV_CLAUDE_CONTEXT_LOCAL_STORAGE = "CLAUDE_CONTEXT_LOCAL_STORAGE"
ENV_CODEX_HOME = "CODEX_HOME"
ENV_CODE_SEARCH_STORAGE = "CODE_SEARCH_STORAGE"
ENV_HF_HOME = "HF_HOME"
ENV_HOME = "HOME"
ENV_INSTALLER = "INSTALLER"
ENV_OPENCODE_CONFIG = "OPENCODE_CONFIG"
ENV_OPENCODE_CONFIG_DIR = "OPENCODE_CONFIG_DIR"
ENV_PATH = "PATH"
ENV_PIPX_BIN_DIR = "PIPX_BIN_DIR"
ENV_PIPX_HOME = "PIPX_HOME"
ENV_SUDO_USER = "SUDO_USER"
ENV_UV_CACHE_DIR = "UV_CACHE_DIR"
ENV_UV_TOOL_BIN_DIR = "UV_TOOL_BIN_DIR"
ENV_UV_TOOL_DIR = "UV_TOOL_DIR"
ENV_XDG_CACHE_HOME = "XDG_CACHE_HOME"
ENV_XDG_CONFIG_HOME = "XDG_CONFIG_HOME"
ENV_XDG_DATA_HOME = "XDG_DATA_HOME"
FILE_MODE_READ_BINARY = "rb"
HARNESS_ALL = "all"
KEY_ACTIONS = "actions"
KEY_ARGS = "args"
KEY_CATEGORY = "category"
KEY_CLEANUP_DIR = "cleanup_dir"
OPTION_OUTPUT_JSON = "--output=json"
PATH_APPLICATIONS = "applications"
PATH_AUTOSTART = "autostart"
PATH_BUN_INSTALL_GLOBAL_NODE_MODULES = ".bun/install/global/node_modules"
PATH_CACHE = ".cache"
PATH_CLAUDE_JSON = ".claude.json*"
PATH_CMDLINE = "cmdline"
PATH_CONF = "*.conf"
PATH_CONFIG_SYSTEMD_USER = ".config/systemd/user"
PATH_CRONTAB_TXT = "crontab.txt"
PATH_DESKTOP = "*.desktop"
PATH_DIST_INFO = "*.dist-info"
PATH_DOT_BIN = ".dot/bin"
PATH_ENVIRONMENT_D = "environment.d"
PATH_ETC_CRONTAB = "/etc/crontab"
PATH_ETC_CRON_D = "/etc/cron.d"
PATH_FISH = "*.fish"
PATH_FISH_CONF_D = "fish/conf.d"
PATH_GIT = ".git"
PATH_HUGGINGFACE = "huggingface"
PATH_LIB_NODE_MODULES = "*/lib/node_modules"
PATH_LIB_PYTHON_SITE_PACKAGES_DIST_INFO = "lib/python*/site-packages/*.dist-info"
PATH_LIB_PYTHON_SITE_PACKAGES_PIP_MAIN_PY = "lib/python*/site-packages/pip/__main__.py"
PATH_LOCAL_BIN = ".local/bin"
PATH_LOCAL_LIB_NODE_MODULES = ".local/lib/node_modules"
PATH_LOCAL_LIB_PYTHON_SITE_PACKAGES = ".local/lib/python*/site-packages"
PATH_LOCAL_PIPX_VENVS = ".local/pipx/venvs"
PATH_LOCAL_SHARE = ".local/share"
PATH_LOCAL_SHARE_SYSTEMD_USER = ".local/share/systemd/user"
PATH_LOCAL_STATE_MCP_CLEANUP_BACKUPS = ".local/state/mcp-cleanup-backups"
PATH_MANIFEST_JSON = "manifest.json"
PATH_NODE_MODULES = "*/node_modules"
PATH_NPM_NPX = ".npm/_npx"
PATH_NVM_VERSIONS_NODE = ".nvm/versions/node"
PATH_OPENCODE_NODE_MODULES = "opencode/node_modules"
PATH_PATTERN = "*"
PATH_PIPX_VENVS = "pipx/venvs"
PATH_PROC = "/proc"
PATH_ROOT_DIRECTORY = "/"
PATH_STAT = "stat"
PATH_SYSTEMD_USER = "systemd/user"
PATH_USR_LIB_NODE_MODULES = "/usr/lib/node_modules"
PATH_USR_LOCAL_LIB_NODE_MODULES = "/usr/local/lib/node_modules"
PATH_UV_TOOLS = "uv/tools"
PATH_VENVS = ".venvs"
PATH_VENVS_LOWERCASE = "venvs"
PATH_VIRTUALENVS = ".virtualenvs"
SHELL_ALIAS_PATTERN = "alias\\s+([\\w-]+)="
SHELL_ASSIGNMENT_PATTERN = "(?:export\\s+)?([A-Za-z_][A-Za-z_0-9]*)="
CONFIG_EXTENSION_PATTERN = "\\.(?:jsonc?|toml|yaml|yml|code-workspace)(?:$|[.-])"
SHORT_OPTION_B = "-B"
SHORT_OPTION_E = "-E"
SHORT_OPTION_I = "-I"
SHORT_OPTION_L = "-l"
SHORT_OPTION_M = "-m"
SHORT_OPTION_P = "-P"
SHORT_OPTION_S = "-s"
SHORT_OPTION_S_CASE_SENSITIVE = "-S"
SHORT_OPTION_U = "-u"
SHORT_OPTION_Y = "-y"
VALUE_CATALOG = "catalog"
VALUE_CLEAN_EXISTING_INSTALLATIONS_AND_CONFIGS_PY = "clean_existing_installations_and_configs.py"
VALUE_HOOKS = "hooks"
VALUE_LINUX = "linux"
VALUE_MCP_SERVER_TOOLS_CACHE = "mcp-server-tools-cache"
VALUE_PLUGIN_JSON = "plugin.json"
VALUE_PYTORCH_MODEL_BIN = "pytorch_model.bin"
VALUE_PYVENV_CFG = "pyvenv.cfg"
VALUE_REVIEW = "review"
VALUE_RUN = "run"
VALUE_UV = "uv"

KEY_CLEANUP_IDENTITY = "cleanup_identity"
KEY_COMMANDS = "commands"
KEY_CONFIGS = "configs"
KEY_CONFIG_FILES_EXAMINED = "config_files_examined"
KEY_COUNTS = "counts"
KEY_CRONTAB = "crontab"
KEY_CWD = "cwd"
KEY_DRY_RUN = "dry_run"
KEY_EDIT = "edit"
KEY_ENTRIES = "entries"
KEY_ENTRY = "entry"
KEY_ENVIRONMENT = "environment"
KEY_EVIDENCE = "evidence"
KEY_EXECUTABLE = "executable"
KEY_FIELD = "field"
KEY_FINDINGS = "findings"
KEY_HOME = "home"
KEY_HOST = "host"
KEY_IDENTITY = "identity"
KEY_INJECTED_PACKAGES = "injected_packages"
KEY_INSTALLER = "installer"
KEY_KIND = "kind"
KEY_LINES = "lines"
KEY_MAIN_PACKAGE = "main_package"
KEY_MANAGER = "manager"
KEY_MATCH = "match"
KEY_MATCHED_FIELDS = "matched_fields"
KEY_MATCHED_NAME = "matched_name"
KEY_MATCHES = "matches"
KEY_MAX_CONTENT_WIDTH = "max_content_width"
KEY_MODELS_PRESERVED = "models_preserved"
KEY_PATH = "path"
KEY_PID = "pid"
KEY_PORT = "port"
KEY_PPID = "ppid"
KEY_PROCESS = "process"
KEY_PROJECTS = "projects"
KEY_PROJECT_ROOT = "."
KEY_REASON = "reason"
KEY_REMOVE = "remove"
KEY_REMOVE_ALL = "remove_all"
KEY_REMOVE_INDEXES = "remove_indexes"
KEY_REMOVE_RUNTIME_PACKAGES = "remove_runtime_packages"
KEY_REQUIREMENTS = "requirements"
KEY_RESOLVED = "resolved"
KEY_RESOLVED_PARENT = "resolved_parent"
KEY_SCOPE = "scope"
KEY_START_TICKS = "start_ticks"
KEY_STATE = "state"
KEY_STORAGE = "storage"
KEY_SYMLINK = "symlink"
KEY_SYSTEM = "system"
KEY_TARGET = "target"
KEY_TARGETS = "targets"
KEY_UID = "uid"
KEY_UNIT = "unit"
LANGUAGE_PYTHON = "python"
LOOPBACK_IPV4 = "127.0.0.1"
OPTION_ALL = "--all"
OPTION_APPLY = "--apply"
OPTION_BACKUP_DIR = "--backup-dir"
OPTION_DIRECTORY = "--directory"
OPTION_DRY_RUN = "--dry-run"
OPTION_EXTRA_INDEX_URL = "--extra-index-url"
OPTION_FROM = "--from"
OPTION_GRACE_SECONDS = "--grace-seconds"
OPTION_HOME = "--home"
OPTION_INDEX = "--index"
OPTION_INDEX_URL = "--index-url"
OPTION_JSON = "--json"
OPTION_NO_BLOCK = "--no-block"
OPTION_NO_PAGER = "--no-pager"
OPTION_PROJECT = "--project"
OPTION_PROJECT_ROOT = "--project-root"
OPTION_PYTHON = "--python"
OPTION_REMOVE_ALL = "--remove-all"
OPTION_REMOVE_INDEXES = "--remove-indexes"
OPTION_REMOVE_RUNTIME_PACKAGES = "--remove-runtime-packages"
OPTION_REVIEWED = "--reviewed"
OPTION_SCAN_ROOT = "--scan-root"
OPTION_SCOPE = "--scope"
OPTION_STORAGE = "--storage"
OPTION_USER = "--user"
OPTION_WITH = "--with"
OPTION_WITH_EDITABLE = "--with-editable"
PACKAGE_NAME = "code_search_local"
PATH_AUTH_JSON = "auth.json"
PATH_BIN_PYTHON = "bin/python"
PATH_CONFIG = ".config"
PATH_CONFIG_JSON = "config.json"
PATH_EMBEDDING_CACHE_SQLITE3 = "embedding-cache.sqlite3"
PATH_INSTALLATION_JSON = "installation.json"
PATH_PATH = ".path"
PATH_PYPROJECT_TOML = "pyproject.toml"
PATH_README_MD = "README.md"
PATH_SERVICE = ".service"
PATH_SETTINGS_JSON = "settings.json"
PATH_STATE_SQLITE3 = "state.sqlite3"
PATH_TIMER = ".timer"
PATH_TOML = ".toml"
PATH_UV_LOCK = "uv.lock"
PATH_VENV = ".venv"
TEXT_ENCODING = "utf-8"
CLI_DESTINATION_JSON = "as_json"
BIN_DIRECTORY = "bin"
TOKEN_ENABLED = "enabled"
TOKEN_ENV = "env"
KEY_MCP = "mcp"
KEY_MCP_SERVERS = "mcp_servers"
MERKLE_DIRECTORY = "merkle"
MODEL_CACHE_DIRECTORY = "models"
TOKEN_NAME = "name"
INSTALL_MODE_PACKAGE = "package"
TOKEN_PLUGIN = "plugin"
TOKEN_PLUGINS = "plugins"
RUNTIMES_DIRECTORY = "runtimes"
KEY_SOURCE = "source"
TOKEN_TOOL = "tool"
TOKEN_URL = "url"
USER_SCOPE = "user"

READONLY_COMMAND_TIMEOUT_SECONDS = 15
MAX_REPORTED_REFERENCE_LOCATIONS = 25
CONFIG_SCAN_DEPTH = 10
RUNTIME_SCAN_DEPTH = 9
LAUNCHER_HEADER_BYTES = 4096
PROC_STATE_INDEX = 0
PROC_PARENT_PID_INDEX = 1
PROC_START_TICKS_INDEX = 19
PROC_COMMAND_SEPARATOR_LENGTH = 2
CRON_SCHEDULE_FIELDS = 5
CRON_MACRO_FIELDS = 1
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
JSON_INDENT = 2
FORCED_EXIT_TIMEOUT_SECONDS = 3
PROCESS_POLL_SECONDS = 0.1
CLI_MAX_CONTENT_WIDTH = 100
MIN_GRACE_SECONDS = 1
MAX_GRACE_SECONDS = 60
DEFAULT_GRACE_SECONDS = 10
BACKUP_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
CONFIRMATION_TEXT = "REMOVE BOTH INSTALLATIONS"

PATH_BASHRC = ".bashrc"
PATH_BASH_PROFILE = ".bash_profile"
PATH_CJS = ".cjs"
PATH_CLAUDE_CONTEXT_LOCAL_SERVER_PY = "claude_context_local/server.py"
PATH_CLAUDE_PLUGIN = ".claude-plugin"
PATH_CLEANUP = ".cleanup-"
PATH_CODEX_PLUGIN = ".codex-plugin"
PATH_CODE_SEARCH_LOCAL_SERVER_PY = "code_search_local/server.py"
PATH_CODE_WORKSPACE = ".code-workspace"
PATH_D = ".d"
PATH_DIST_INFO_CASE_SENSITIVE = ".dist-info"
PATH_EMBEDDINGS_JSON = "embeddings.json"
PATH_ETC_SYSTEMD_SYSTEM = "/etc/systemd/system"
PATH_ETC_SYSTEMD_USER = "/etc/systemd/user"
PATH_GGML = ".ggml"
PATH_GGUF = ".gguf"
PATH_GZ = ".gz"
PATH_JS = ".js"
PATH_JSON = ".json"
PATH_LIB = "/lib/"
PATH_MCP_SERVER_SERVER_PY = "mcp_server/server.py"
PATH_MJS = ".mjs"
PATH_PAM_ENVIRONMENT = ".pam_environment"
PATH_PIPX_METADATA_JSON = "pipx_metadata.json"
PATH_PROFILE = ".profile"
PATH_RUN_SYSTEMD_SYSTEM = "/run/systemd/system"
PATH_RUN_SYSTEMD_TRANSIENT = "/run/systemd/transient"
PATH_SAFETENSORS = ".safetensors"
PATH_SCOPE = ".scope"
PATH_SOCKET = ".socket"
PATH_SWN = ".swn"
PATH_SWO = ".swo"
PATH_SWP = ".swp"
PATH_TARGET = ".target"
PATH_USR_LIB = "/usr/lib/"
PATH_USR_LIB_SYSTEMD_SYSTEM = "/usr/lib/systemd/system"
PATH_USR_LIB_SYSTEMD_USER = "/usr/lib/systemd/user"
PATH_USR_LOCAL_LIB_SYSTEMD_SYSTEM = "/usr/local/lib/systemd/system"
PATH_USR_LOCAL_LIB_SYSTEMD_USER = "/usr/local/lib/systemd/user"
PATH_UVX_UV_CACHE = "uvx/uv-cache"
PATH_UV_RECEIPT_TOML = "uv-receipt.toml"
PATH_XZ = ".xz"
PATH_ZIP = ".zip"
PATH_ZPROFILE = ".zprofile"
PATH_ZSHRC = ".zshrc"
PATH_ZST = ".zst"
TOKEN_ = "--"
TOKEN_ACTIVATING = "activating"
TOKEN_ACTIVE = "active"
TOKEN_ALIAS = "alias"
TOKEN_ALLOW = "allow"
TOKEN_ALLOWEDTOOLS = "allowedtools"
TOKEN_ASK = "ask"
TOKEN_BUN = "bun"
TOKEN_CACHE = "cache"
TOKEN_CLAUDE_CODE_SEARCH = "claude-code-search"
TOKEN_CLAUDE_CODE_SEARCH_CASE_SENSITIVE = "claude_code_search"
TOKEN_CLAUDE_CONTEXT_LOCAL = "claude-context-local"
TOKEN_CLAUDE_CONTEXT_LOCAL_CASE_SENSITIVE = "claude_context_local"
TOKEN_CLEAN = "clean"
TOKEN_COOKIE = "cookie"
TOKEN_CREDENTIALS = "credentials"
TOKEN_DEACTIVATING = "deactivating"
TOKEN_DENY = "deny"
TOKEN_DISABLEDMCPJSONSERVERS = "disabledmcpjsonservers"
TOKEN_DISABLEDTOOLS = "disabledtools"
TOKEN_ENABLEDMCPJSONSERVERS = "enabledmcpjsonservers"
TOKEN_ENABLEDPLUGINS = "enabledplugins"
TOKEN_ENABLED_RUNTIME = "enabled-runtime"
TOKEN_EXTRAKNOWNMARKETPLACES = "extraknownmarketplaces"
TOKEN_GITHUBREPOPATHS = "githubRepoPaths"
TOKEN_HISTORY = "history"
TOKEN_HOOK = "hook"
TOKEN_INDEXES = "indexes"
TOKEN_IS_ACTIVE = "is-active"
TOKEN_IS_ENABLED = "is-enabled"
TOKEN_JOURNAL = "-journal"
TOKEN_LINKED = "linked"
TOKEN_LINKED_RUNTIME = "linked-runtime"
TOKEN_LIST_UNITS = "list-units"
TOKEN_MARKETPLACES = "marketplaces"
TOKEN_MCP = "mcp__"
TOKEN_MCPSERVERS = "mcpservers"
TOKEN_MODELS = "models--"
TOKEN_NODE = "node"
TOKEN_NODE_MODULES = "node_modules"
TOKEN_PIPX = "pipx"
TOKEN_PRESERVED = "preserved"
TOKEN_RELOADING = "reloading"
TOKEN_REPLACE = "replace"
TOKEN_RUNUSER = "runuser"
TOKEN_SERVERS = "servers"
TOKEN_SESSION = "session"
TOKEN_SHM = "-shm"
TOKEN_SKILLS = "skills"
TOKEN_TRANSCRIPT = "transcript"
TOKEN_UNINJECT = "uninject"
TOKEN_UVX = "uvx"
TOKEN_VALUE = "value"
TOKEN_WAL = "-wal"
TOKEN_WB = "wb"

DEAD_PROCESS_STATES = frozenset({"Z", "X"})

USER_RUNTIME_ENV_TEMPLATE = "XDG_RUNTIME_DIR=/run/user/{uid}"
USER_DBUS_ENV_TEMPLATE = "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus"
USER_SYSTEMD_DIRECTORY_TEMPLATE = "/run/user/{uid}/systemd/user"
USER_SYSTEMD_TRANSIENT_TEMPLATE = "/run/user/{uid}/systemd/transient"
MCP_ENDPOINT_TEMPLATE = "http://{host}:{port}/mcp"

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
    ".gemini",
    ".openclaw",
)
CONFIG_APPS = (
    "Claude",
    "claude",
    "Codex",
    "codex",
    "opencode",
    "Cursor",
    "gemini",
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
    ".gemini/settings.json",
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
    match = IDENTITY.match(value.lstrip(KEY_PROJECT_ROOT))
    return bool(
        match
        and (
            match.end() == len(value.lstrip(KEY_PROJECT_ROOT))
            or value.lstrip(KEY_PROJECT_ROOT)[match.end()] in "-_.@/"
        )
    )


def backup_name(name):
    return (
        bool(BACKUP_NAME.search(name))
        or name.endswith("~")
        or name.lower().endswith((PATH_SWP, PATH_SWO, PATH_SWN))
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
        (parent for parent in (resolved, *resolved.parents) if (parent / PATH_GIT).exists()), None
    )


def distribution_name(metadata):
    return (
        metadata.name.removesuffix(PATH_DIST_INFO_CASE_SENSITIVE)
        .rsplit("-", 1)[0]
        .replace("_", "-")
    )


def manager_executable(name):
    candidate = shutil.which(name) or str(Path(sys.executable).parent / name)
    if Path(candidate).is_file() and os.access(candidate, os.X_OK):
        return candidate
    if name == VALUE_UV:
        from uv import find_uv_bin

        return find_uv_bin()
    return None


def readonly(args, *, timeout=READONLY_COMMAND_TIMEOUT_SECONDS):
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


REGISTRATION_FIELDS = (
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


def registration_fields(value):
    return ((key, value[key]) for key in REGISTRATION_FIELDS if key in value)


def registration_reference(value, endpoints=()):
    """Inspect identity/launch fields, not descriptions or an entire mixed marketplace."""
    if isinstance(value, str):
        return contains_reference(value, endpoints)
    if not isinstance(value, dict):
        return False
    return any(contains_reference(child, endpoints) for _, child in registration_fields(value))


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
    if any(VALUE_MCP_SERVER_TOOLS_CACHE in part for part in trail):
        category = "cached MCP discovery entry"
    elif any(part in {KEY_MCP, TOKEN_MCPSERVERS, KEY_MCP_SERVERS, TOKEN_SERVERS} for part in trail):
        category = "MCP registration"
    elif VALUE_HOOKS in trail:
        category = TOKEN_HOOK
    elif any(part in {TOKEN_ENV, KEY_ENVIRONMENT} for part in trail):
        category = "environment setting"
    elif any(part in {TOKEN_MARKETPLACES, TOKEN_EXTRAKNOWNMARKETPLACES} for part in trail):
        category = "marketplace catalog entry"
    elif any(
        part
        in {
            TOKEN_PLUGINS,
            TOKEN_PLUGIN,
            TOKEN_ENABLEDPLUGINS,
            TOKEN_MARKETPLACES,
            TOKEN_EXTRAKNOWNMARKETPLACES,
        }
        for part in trail
    ):
        category = "plugin registration"
    else:
        category = "tool permission or setting"
    fields = []

    def inspect(value, path):
        if isinstance(value, dict):
            for name, child in registration_fields(value):
                inspect(child, f"{path}.{name}" if path else name)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                inspect(child, f"{path}[{index}]")
        elif isinstance(value, str):
            for match in dict.fromkeys(IDENTITY.findall(value)):
                fields.append({KEY_FIELD: path or TOKEN_VALUE, KEY_MATCHED_NAME: match})
            if value in endpoints:
                fields.append(
                    {
                        KEY_FIELD: path or TOKEN_VALUE,
                        KEY_MATCH: "exact service endpoint from installation settings",
                    }
                )

    if key is not None:
        inspect(key, "registration key")
        if ENVIRONMENT.match(key):
            fields.append({KEY_FIELD: "environment variable", KEY_MATCHED_NAME: key})
    inspect(value, "")
    return {KEY_ENTRY: "/" + "/".join(location), KEY_CATEGORY: category, KEY_MATCHED_FIELDS: fields}


def prune(document, endpoints=(), trail=(), removed=None, match_records=None):
    """Remove individual registrations/permissions/hooks, retaining unrelated settings."""
    removed = [] if removed is None else removed
    match_records = [] if match_records is None else match_records
    if isinstance(document, dict):
        registry = bool(trail and str(trail[-1]).lower() in REGISTRIES)
        for key in list(document):
            value = document[key]
            location = (*trail, str(key))
            owned_key = named(str(key)) or str(key).lower().startswith(TOKEN_MCP) and matches(key)
            owned_env = (
                ENVIRONMENT.match(str(key))
                and trail
                and str(trail[-1]).lower() in {TOKEN_ENV, KEY_ENVIRONMENT}
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
                list_kind == VALUE_CATALOG
                and any(VALUE_MCP_SERVER_TOOLS_CACHE in part for part in trail)
            ) or list_kind in REGISTRIES | {
                TOKEN_PLUGIN,
                TOKEN_ALLOW,
                TOKEN_DENY,
                TOKEN_ASK,
                VALUE_HOOKS,
                TOKEN_ENABLEDMCPJSONSERVERS,
                TOKEN_DISABLEDMCPJSONSERVERS,
                TOKEN_ALLOWEDTOOLS,
                TOKEN_DISABLEDTOOLS,
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
                KEY_ENTRIES,
                KEY_MATCHES,
                KEY_LINES,
                KEY_MANAGER,
                KEY_UNIT,
                KEY_PID,
                KEY_EXECUTABLE,
                KEY_CWD,
                KEY_INSTALLER,
                KEY_COMMANDS,
                KEY_ENVIRONMENT,
                KEY_CLEANUP_DIR,
                KEY_SYMLINK,
            }
        }
        target = (
            self.details.get(KEY_RESOLVED, self.target) if self.kind == KEY_EDIT else self.target
        )
        return {KEY_KIND: self.kind, KEY_TARGET: target, KEY_REASON: self.reason, **visible}


class Scanner:
    def __init__(
        self,
        home,
        *,
        scope=HARNESS_ALL,
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
        self.config_home = Path(os.environ.get(ENV_XDG_CONFIG_HOME, home / PATH_CONFIG))
        self.data_home = Path(os.environ.get(ENV_XDG_DATA_HOME, home / PATH_LOCAL_SHARE))
        self.cache_home = Path(os.environ.get(ENV_XDG_CACHE_HOME, home / PATH_CACHE))
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
                (self.cache_home / PATH_HUGGINGFACE).resolve(),
                Path(os.environ.get(ENV_HF_HOME, self.cache_home / PATH_HUGGINGFACE))
                .expanduser()
                .resolve(),
            }
        )
        self.unit_roots = {}
        self.ancestors = set()
        pid = os.getpid()
        while pid:
            self.ancestors.add(pid)
            item = process_info(Path(PATH_PROC) / str(pid))
            pid = item[KEY_PPID] if item else 0

    def protected_path(self, path):
        resolved = path.resolve()
        if source_worktree(resolved):
            return True
        shared = {
            Path(PATH_ROOT_DIRECTORY),
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

    def finding(self, path, reason, *, category=VALUE_REVIEW, **details):
        item = {KEY_PATH: str(path), KEY_REASON: reason, KEY_CATEGORY: category, **details}
        if item not in self.findings:
            self.findings.append(item)

    def add(self, action):
        if action.kind in {KEY_EDIT, KEY_REMOVE, INSTALL_MODE_PACKAGE} and backup_path(
            action.target
        ):
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
                    category=TOKEN_PRESERVED,
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
                    KEY_REMOVE,
                    str(path),
                    reason,
                    {
                        KEY_IDENTITY: fingerprint(path),
                        KEY_RESOLVED_PARENT: str(path.parent.resolve()),
                        KEY_SYMLINK: path.is_symlink(),
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
            text = raw.decode(TEXT_ENCODING)
            if not (
                matches(text)
                or any(endpoint in text for endpoint in self.endpoints)
                or '"projects"' in text
                or "[projects." in text
            ):
                return
            if PATH_TOML in path.name:
                doc = tomlkit.parse(text)
                encode = tomlkit.dumps
            elif any(ext in path.name for ext in (PATH_JSON, PATH_CODE_WORKSPACE)):
                try:
                    doc = json.loads(text)
                except ValueError:
                    doc = json5.loads(text)
                encode = lambda value: (
                    json.dumps(value, indent=JSON_INDENT, ensure_ascii=False) + "\n"
                )
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
                    doc.get(KEY_PROJECTS, {}) if isinstance(doc.get(KEY_PROJECTS), dict) else ()
                ):
                    if project.startswith("/") and Path(project).is_dir():
                        self.projects.add(Path(project).resolve())
            match_records = []
            removed = prune(doc, self.endpoints, match_records=match_records)
            if removed:
                kinds = list(dict.fromkeys(record[KEY_CATEGORY] for record in match_records))
                self.add(
                    Action(
                        KEY_EDIT,
                        str(path),
                        "Remove matched Code Search Local entries: " + ", ".join(kinds),
                        {
                            KEY_ENTRIES: removed,
                            KEY_MATCHES: match_records,
                            KEY_RESOLVED: str(path.resolve()),
                            KEY_IDENTITY: fingerprint(path),
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
                    location and location[0] in {KEY_PROJECTS, TOKEN_GITHUBREPOPATHS}
                    for location in locations
                )
                self.finding(
                    path,
                    "Workspace references retained"
                    if workspace_only
                    else "Additional reference outside a recognized registration; inspect manually",
                    category=TOKEN_PRESERVED if workspace_only else VALUE_REVIEW,
                    entries=[
                        "/" + "/".join(location)
                        for location in locations[:MAX_REPORTED_REFERENCE_LOCATIONS]
                    ],
                )
        except (OSError, ValueError, TypeError) as error:
            if not text or matches(text):
                self.finding(
                    path, f"Cannot parse/read config ({error.__class__.__name__}); not edited"
                )

    def walk_configs(self, base, *, depth=CONFIG_SCAN_DEPTH):
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
                        TOKEN_HISTORY,
                        TOKEN_TRANSCRIPT,
                        PATH_AUTH_JSON,
                        TOKEN_CREDENTIALS,
                        TOKEN_COOKIE,
                        TOKEN_SESSION,
                        PATH_EMBEDDINGS_JSON,
                    )
                ):
                    continue
                if not name.endswith((PATH_GZ, PATH_ZIP, PATH_ZST, PATH_XZ)) and re.search(
                    CONFIG_EXTENSION_PATTERN, name
                ):
                    self.config(Path(root) / name)

    def app_state(self):
        aliases = (
            APPLICATION_NAME,
            PACKAGE_NAME,
            TOKEN_CLAUDE_CONTEXT_LOCAL,
            TOKEN_CLAUDE_CONTEXT_LOCAL_CASE_SENSITIVE,
            TOKEN_CLAUDE_CODE_SEARCH,
            TOKEN_CLAUDE_CODE_SEARCH_CASE_SENSITIVE,
        )
        for alias in aliases:
            for base in (self.home, self.data_home, self.cache_home):
                path = base / ((KEY_PROJECT_ROOT + alias) if base == self.home else alias)
                if backup_path(path):
                    continue
                if path.is_dir():
                    self.storage.add(path.resolve())
                if path.is_symlink():
                    self.finding(
                        path,
                        "Storage alias retained so models and retained data stay accessible",
                        category=TOKEN_PRESERVED,
                    )
            root = self.config_home / alias
            if not root.is_dir() or backup_path(root):
                continue
            for name in (PATH_CONFIG_JSON, PATH_SETTINGS_JSON, PATH_INSTALLATION_JSON):
                path = root / name
                if not path.is_file() or backup_path(path):
                    continue
                try:
                    doc = json5.loads(path.read_text())
                    if doc.get(KEY_STORAGE):
                        self.storage.add(Path(doc[KEY_STORAGE]).expanduser().resolve())
                    if doc.get(KEY_SOURCE):
                        self.protected.add(Path(doc[KEY_SOURCE]).resolve())
                    if KEY_PORT in doc:
                        host = doc.get(KEY_HOST, LOOPBACK_IPV4)
                        self.endpoints.add(
                            MCP_ENDPOINT_TEMPLATE.format(
                                host=("[" + host + "]") if ":" in host else host, port=doc[KEY_PORT]
                            )
                        )
                    for target in doc.get(KEY_TARGETS, []):
                        for config in target.get(KEY_CONFIGS, []):
                            self.config(config)
                except (OSError, ValueError, TypeError) as error:
                    self.finding(
                        path, f"Cannot read installation metadata ({error.__class__.__name__})"
                    )
            self.delete(root, "Remove plugin service configuration and installation metadata")
        for name in (
            ENV_CODE_SEARCH_STORAGE,
            ENV_CLAUDE_CONTEXT_LOCAL_STORAGE,
            ENV_CLAUDE_CODE_SEARCH_STORAGE,
        ):
            if os.environ.get(name):
                self.storage.add(Path(os.environ[name]).expanduser().resolve())

    def profiles(self):
        roots = {self.home / name for name in HARNESSES}
        roots.update(self.config_home / name for name in CONFIG_APPS)
        for key in (ENV_CODEX_HOME, ENV_CLAUDE_CONFIG_DIR, ENV_OPENCODE_CONFIG_DIR):
            if os.environ.get(key):
                roots.add(Path(os.environ[key]).expanduser())
        for key in (ENV_OPENCODE_CONFIG,):
            if os.environ.get(key):
                self.config(Path(os.environ[key]).expanduser())
        for path in self.home.glob(PATH_CLAUDE_JSON):
            self.config(path)
        for root in sorted(roots):
            if backup_path(root):
                continue
            self.walk_configs(root)
            # Only managed plugin/skill cache locations: never delete the agent application itself.
            for subdir in (
                TOKEN_PLUGINS,
                TOKEN_SKILLS,
                "Claude Extensions",
                "Claude Extensions Settings",
            ):
                managed = root / subdir
                if not managed.is_dir() or backup_path(managed):
                    continue
                for directory, dirs, files in os.walk(managed, followlinks=False):
                    dirs[:] = [
                        name
                        for name in dirs
                        if name not in {TOKEN_NODE_MODULES, PATH_GIT}
                        and not backup_path(Path(directory) / name)
                    ]
                    if VALUE_PLUGIN_JSON in files and not backup_path(
                        Path(directory) / VALUE_PLUGIN_JSON
                    ):
                        try:
                            manifest = json.loads((Path(directory) / VALUE_PLUGIN_JSON).read_text())
                            if named(str(manifest.get(TOKEN_NAME, ""))):
                                owner = Path(directory)
                                if owner.name in {PATH_CLAUDE_PLUGIN, PATH_CODEX_PLUGIN}:
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
        if self.scope != KEY_SYSTEM:
            self.unit_roots[USER_SCOPE] = [
                self.home / PATH_CONFIG_SYSTEMD_USER,
                self.config_home / PATH_SYSTEMD_USER,
                self.home / PATH_LOCAL_SHARE_SYSTEMD_USER,
                Path(USER_SYSTEMD_DIRECTORY_TEMPLATE.format(uid=self.uid)),
                Path(USER_SYSTEMD_TRANSIENT_TEMPLATE.format(uid=self.uid)),
            ]
        if self.scope != USER_SCOPE:
            self.unit_roots[KEY_SYSTEM] = [
                Path(p)
                for p in (
                    PATH_ETC_SYSTEMD_SYSTEM,
                    PATH_RUN_SYSTEMD_SYSTEM,
                    PATH_RUN_SYSTEMD_TRANSIENT,
                    PATH_USR_LOCAL_LIB_SYSTEMD_SYSTEM,
                    PATH_USR_LIB_SYSTEMD_SYSTEM,
                )
            ]
            self.unit_roots.setdefault(USER_SCOPE, []).extend(
                Path(p)
                for p in (
                    PATH_ETC_SYSTEMD_USER,
                    PATH_USR_LOCAL_LIB_SYSTEMD_USER,
                    PATH_USR_LIB_SYSTEMD_USER,
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
                                            KEY_ARGS: shlex.split(
                                                line.partition("=")[2].lstrip("-+!:")
                                            ),
                                            KEY_CWD: str(path.parent),
                                        }
                                    )
                                except ValueError:
                                    pass
                        if matches(content) and not (
                            named(name)
                            or owned_launch
                            or named(path.parent.name.removesuffix(PATH_D))
                        ):
                            self.finding(path, "Reference in an unrelated unit; inspect manually")
                        if (
                            named(name)
                            or owned_launch
                            or named(path.parent.name.removesuffix(PATH_D))
                            or path.is_symlink()
                            and named(Path(os.readlink(path)).name)
                        ):
                            unit = name
                            if PATH_D in path.parent.suffixes:
                                unit = path.parent.name.removesuffix(PATH_D)
                            if not unit.endswith(
                                (
                                    PATH_SERVICE,
                                    PATH_SOCKET,
                                    PATH_PATH,
                                    PATH_TIMER,
                                    PATH_TARGET,
                                    PATH_SCOPE,
                                )
                            ):
                                self.finding(
                                    path, "Reference in a systemd fragment; verify owner manually"
                                )
                                continue
                            # A mixed drop-in for an unrelated service must not stop that service.
                            if path.parent.name.endswith(PATH_D) and not named(unit):
                                self.finding(
                                    path,
                                    "Matching drop-in belongs to an unrelated unit; not stopped automatically",
                                )
                                continue
                            self.add(
                                Action(
                                    KEY_UNIT,
                                    f"{manager}:{unit}",
                                    "Uninstall matching systemd unit: stop/disable; unit-file removals listed separately",
                                    {KEY_MANAGER: manager, KEY_UNIT: unit},
                                )
                            )
                            if (
                                str(path).startswith((PATH_USR_LIB, PATH_LIB))
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
                                    if source.is_dir() and (source / PATH_PYPROJECT_TOML).is_file():
                                        self.protected.add(source.resolve())
                                if line.startswith("ExecStart="):
                                    try:
                                        args = shlex.split(line.partition("=")[2])
                                        if OPTION_STORAGE in args:
                                            self.storage.add(
                                                Path(args[args.index(OPTION_STORAGE) + 1])
                                                .expanduser()
                                                .resolve()
                                            )
                                    except (ValueError, IndexError):
                                        self.finding(
                                            path, "Cannot parse storage option in ExecStart"
                                        )
        # Include loaded transient/deleted units that have no remaining unit file.
        for manager in self.unit_roots:
            if manager == USER_SCOPE and self.uid != os.getuid():
                self.finding(
                    self.home,
                    "User-manager runtime query skipped for another UID; unit files still scanned",
                )
                continue
            args = [
                COMMAND_SYSTEMCTL,
                *([OPTION_USER] if manager == USER_SCOPE else []),
                TOKEN_LIST_UNITS,
                OPTION_ALL,
                OPTION_NO_PAGER,
                OPTION_OUTPUT_JSON,
            ]
            try:
                result = readonly(args)
                if result.returncode:
                    self.finding(manager, "Cannot query systemd manager; unit files still scanned")
                    continue
                for entry in json.loads(result.stdout):
                    name = entry.get(KEY_UNIT, "")
                    if named(name):
                        self.add(
                            Action(
                                KEY_UNIT,
                                f"{manager}:{name}",
                                "Uninstall matching loaded systemd unit: stop/disable; unit-file removals listed separately",
                                {KEY_MANAGER: manager, KEY_UNIT: name},
                            )
                        )
            except (OSError, ValueError, subprocess.SubprocessError):
                self.finding(
                    manager, "Systemd runtime inventory unavailable; unit files still scanned"
                )

    def processes(self, proc=Path(PATH_PROC)):
        inventory = {}
        for path in proc.iterdir():
            if path.name.isdigit():
                info = process_info(path)
                if (
                    info
                    and info[KEY_STATE] not in DEAD_PROCESS_STATES
                    and info[KEY_UID] == self.uid
                    and info[KEY_PID] not in self.ancestors
                ):
                    inventory[info[KEY_PID]] = info
        owned = {pid for pid, info in inventory.items() if owned_process(info)}
        while True:
            children = {pid for pid, info in inventory.items() if info[KEY_PPID] in owned}
            if children <= owned:
                break
            owned.update(children)
        for pid in sorted(owned):
            info = inventory[pid]
            cwd = Path(info[KEY_CWD])
            if matches(str(cwd)) and (
                (cwd / PATH_PYPROJECT_TOML).exists() or (cwd / PATH_GIT).exists()
            ):
                self.protected.add(cwd.resolve())
            self.add(
                Action(
                    KEY_PROCESS,
                    str(pid),
                    "Stop matching server/launcher or its descendant",
                    {
                        KEY_PID: pid,
                        KEY_START_TICKS: info[KEY_START_TICKS],
                        KEY_UID: info[KEY_UID],
                        KEY_EXECUTABLE: info[KEY_ARGS][0] if info[KEY_ARGS] else "",
                        KEY_CWD: info[KEY_CWD],
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
            path.name.endswith((PATH_SAFETENSORS, PATH_GGUF, PATH_GGML))
            or path.name == VALUE_PYTORCH_MODEL_BIN
        ):
            return "Downloaded models are always preserved"
        for root, dirs, files in os.walk(path, followlinks=False):
            if any(
                (Path(root) / name).is_symlink() and source_worktree(Path(root) / name)
                for name in dirs
            ):
                return "Contains a link into a source worktree"
            if PATH_GIT in dirs or PATH_GIT in files:
                return "Contains a source clone/worktree"
            if any(name.startswith(TOKEN_MODELS) for name in dirs) or any(
                name.endswith((PATH_SAFETENSORS, PATH_GGUF, PATH_GGML))
                or name == VALUE_PYTORCH_MODEL_BIN
                for name in files
            ):
                return "Contains downloaded models, which are always preserved"
            if not environment and VALUE_PYVENV_CFG in files:
                return "Contains a runtime environment; only its original installer may remove it"
            if any(
                backup_name(name)
                or (Path(root) / name).is_symlink()
                and backup_path(Path(root) / name)
                for name in (*dirs, *files)
            ):
                return "Contains backups; preserve them and remove only eligible siblings"
        return None

    def runtime_removal_enabled(self, target):
        if self.remove_runtime_packages:
            return True
        self.finding(
            target,
            "Runtime/package retained; requires --remove-runtime-packages",
            category=TOKEN_PRESERVED,
        )
        return False

    def package_action(self, target, commands, installer, evidence, *, env=None, cleanup_dir=None):
        target = Path(target).absolute()
        if backup_path(target):
            return
        if not self.runtime_removal_enabled(target):
            return
        for path in (target, Path(cleanup_dir) if cleanup_dir else target):
            reason = self.artifact_guard(path, environment=True)
            if reason:
                self.finding(path, reason, category=TOKEN_PRESERVED)
                return
        if any(not command or not command[0] for command in commands):
            self.finding(target, "Original installer is unavailable; package/environment retained")
            return
        details = {
            KEY_INSTALLER: installer,
            KEY_COMMANDS: commands,
            KEY_ENVIRONMENT: env or {},
            KEY_IDENTITY: fingerprint(target),
            KEY_RESOLVED: str(target.resolve()),
            KEY_EVIDENCE: {str(p): digest(p.read_bytes()) for p in evidence},
        }
        if cleanup_dir:
            details.update(
                cleanup_dir=str(cleanup_dir), cleanup_identity=fingerprint(Path(cleanup_dir))
            )
        self.add(
            Action(
                INSTALL_MODE_PACKAGE,
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
        metadata = sorted(venv.glob(PATH_LIB_PYTHON_SITE_PACKAGES_DIST_INFO))
        selected = metadata if managed_root else [p for p in metadata if named(p.name)]
        if not selected:
            return
        if not self.runtime_removal_enabled(venv):
            return
        if self.artifact_guard(venv, environment=True):
            self.finding(
                venv, self.artifact_guard(venv, environment=True), category=TOKEN_PRESERVED
            )
            return
        python = venv / PATH_BIN_PYTHON
        if not python.is_file() or not (venv / VALUE_PYVENV_CFG).is_file():
            self.finding(
                venv, "Missing venv interpreter/marker; no installer command can be selected"
            )
            return
        groups, evidence = {}, [venv / VALUE_PYVENV_CFG]
        for entry in selected:
            receipt = entry / ENV_INSTALLER
            owner = receipt.read_text().strip() if receipt.is_file() else ""
            if owner not in {COMMAND_PIP, VALUE_UV}:
                self.finding(entry, "Unknown/missing INSTALLER metadata; environment retained")
                return
            groups.setdefault(owner, []).append(distribution_name(entry))
            evidence.append(receipt)
        commands = []
        for owner, packages in sorted(groups.items()):
            if owner == VALUE_UV:
                commands.append(
                    [
                        manager_executable(VALUE_UV),
                        COMMAND_PIP,
                        COMMAND_UNINSTALL,
                        OPTION_PYTHON,
                        str(python),
                        *packages,
                    ]
                )
            else:
                if not list(venv.glob(PATH_LIB_PYTHON_SITE_PACKAGES_PIP_MAIN_PY)):
                    self.finding(
                        venv,
                        "pip installed this distribution but is unavailable in this environment; retained",
                    )
                    return
                commands.append(
                    [
                        str(python),
                        SHORT_OPTION_M,
                        COMMAND_PIP,
                        COMMAND_UNINSTALL,
                        SHORT_OPTION_Y,
                        *packages,
                    ]
                )
        # Only our dedicated generated runtime may lose its whole environment after uninstall.
        if managed_root:
            evidence.extend([managed_root / PATH_README_MD, managed_root / PATH_UV_LOCK])
        self.package_action(
            venv, commands, "+".join(sorted(groups)), evidence, cleanup_dir=managed_root
        )

    def installations(self):
        tool_roots = {
            self.data_home / PATH_UV_TOOLS: VALUE_UV,
            self.data_home / PATH_PIPX_VENVS: TOKEN_PIPX,
            self.home / PATH_LOCAL_PIPX_VENVS: TOKEN_PIPX,
        }
        if os.environ.get(ENV_UV_TOOL_DIR):
            tool_roots[Path(os.environ[ENV_UV_TOOL_DIR])] = VALUE_UV
        if os.environ.get(ENV_PIPX_HOME):
            tool_roots[Path(os.environ[ENV_PIPX_HOME]) / PATH_VENVS_LOWERCASE] = TOKEN_PIPX
        for root, installer in tool_roots.items():
            if not root.is_dir() or backup_path(root):
                continue
            for venv in sorted(root.iterdir()):
                if not venv.is_dir() or backup_path(venv):
                    continue
                self.package_envs.add(venv.resolve())
                receipt = venv / (
                    PATH_UV_RECEIPT_TOML if installer == VALUE_UV else PATH_PIPX_METADATA_JSON
                )
                if backup_path(receipt):
                    continue
                try:
                    doc = (
                        tomlkit.parse(receipt.read_text())
                        if installer == VALUE_UV
                        else json.loads(receipt.read_text())
                    )
                    if installer == VALUE_UV:
                        packages = [
                            r[TOKEN_NAME]
                            for r in doc.get(TOKEN_TOOL, {}).get(KEY_REQUIREMENTS, [])
                            if named(r.get(TOKEN_NAME, ""))
                        ]
                        if not packages:
                            continue
                        commands = [
                            [manager_executable(VALUE_UV), TOKEN_TOOL, COMMAND_UNINSTALL, *packages]
                        ]
                        env = {ENV_UV_TOOL_DIR: str(root)}
                    else:
                        package = doc.get(KEY_MAIN_PACKAGE, {}).get(INSTALL_MODE_PACKAGE, "")
                        if named(package):
                            commands = [
                                [manager_executable(TOKEN_PIPX), COMMAND_UNINSTALL, venv.name]
                            ]
                        else:
                            injected = [p for p in doc.get(KEY_INJECTED_PACKAGES, {}) if named(p)]
                            if not injected:
                                continue
                            commands = [
                                [
                                    manager_executable(TOKEN_PIPX),
                                    TOKEN_UNINJECT,
                                    venv.name,
                                    *injected,
                                ]
                            ]
                        env = {ENV_PIPX_HOME: str(root.parent)}
                    self.package_action(venv, commands, installer, [receipt], env=env)
                except (OSError, ValueError, TypeError, KeyError):
                    if named(venv.name):
                        self.finding(
                            venv,
                            "Installer receipt missing/malformed; environment retained",
                            category=VALUE_REVIEW
                            if self.remove_runtime_packages
                            else TOKEN_PRESERVED,
                        )
        # Find console entry points without deleting them behind their installer's back.
        bins = {self.home / PATH_LOCAL_BIN, self.home / BIN_DIRECTORY, self.home / PATH_DOT_BIN}
        bins.update(Path(p) for p in os.environ.get(ENV_PATH, "").split(os.pathsep) if p)
        for key in (ENV_UV_TOOL_BIN_DIR, ENV_PIPX_BIN_DIR):
            if os.environ.get(key):
                bins.add(Path(os.environ[key]))
        for root in sorted(bins):
            if (
                backup_path(root)
                or not root.is_dir()
                or self.scope == USER_SCOPE
                and not os.access(root, os.W_OK)
            ):
                continue
            for path in root.iterdir():
                if not named(path.name) or backup_path(path):
                    continue
                owner = path.resolve().parent.parent
                if not (owner / VALUE_PYVENV_CFG).is_file():
                    try:
                        header = (
                            path.open(FILE_MODE_READ_BINARY)
                            .readline(LAUNCHER_HEADER_BYTES)
                            .decode()
                            .strip()
                        )
                        if header.startswith("#!"):
                            owner = Path(shlex.split(header[2:])[0]).parent.parent
                    except (OSError, UnicodeError, ValueError, IndexError):
                        pass
                if (owner / VALUE_PYVENV_CFG).is_file():
                    self.python_environment(owner)
                else:
                    self.finding(
                        path,
                        "Launcher retained; original installer ownership is unknown",
                        category=VALUE_REVIEW if self.remove_runtime_packages else TOKEN_PRESERVED,
                    )
        env_roots = [self.home / PATH_VENVS, self.home / PATH_VIRTUALENVS]
        for project in self.projects:
            env_roots.extend([project / PATH_VENV, project / PATH_VENVS])
        for root in env_roots:
            if root.is_dir() and not backup_path(root):
                if (root / VALUE_PYVENV_CFG).is_file():
                    self.python_environment(root)
                for candidate in root.iterdir():
                    if candidate.is_dir() and (candidate / VALUE_PYVENV_CFG).is_file():
                        self.python_environment(candidate)
        for root in sorted(self.storage):
            runtimes = root / RUNTIMES_DIRECTORY
            if not runtimes.is_dir() or backup_path(runtimes):
                continue
            for runtime in sorted(runtimes.iterdir()):
                if backup_path(runtime):
                    continue
                marker = runtime / PATH_README_MD
                if backup_path(marker) or backup_path(runtime / PATH_UV_LOCK):
                    continue
                if (
                    marker.is_file()
                    and marker.read_text().strip() == "Managed code-search-local runtime."
                    and (runtime / PATH_UV_LOCK).is_file()
                ):
                    self.python_environment(runtime / PATH_VENV, managed_root=runtime)
                else:
                    self.finding(
                        runtime,
                        "Unrecognized runtime provenance; environment retained",
                        category=VALUE_REVIEW if self.remove_runtime_packages else TOKEN_PRESERVED,
                    )
        # uvx environments and package caches are owned by uv. Never rmtree cache internals.
        uv_cache = Path(os.environ.get(ENV_UV_CACHE_DIR, self.cache_home / VALUE_UV))
        if uv_cache.is_dir() and not backup_path(uv_cache):
            packages = set()
            for directory, dirs, _ in os.walk(uv_cache, followlinks=False):
                depth = len(Path(directory).relative_to(uv_cache).parts)
                dirs[:] = [d for d in dirs if not backup_name(d) and depth < RUNTIME_SCAN_DEPTH]
                for name in dirs:
                    if name.endswith(PATH_DIST_INFO_CASE_SENSITIVE) and named(name):
                        packages.add(distribution_name(Path(name)))
            if packages:
                self.package_action(
                    uv_cache,
                    [[manager_executable(VALUE_UV), TOKEN_CACHE, TOKEN_CLEAN, *sorted(packages)]],
                    PATH_UVX_UV_CACHE,
                    [],
                    env={ENV_UV_CACHE_DIR: str(uv_cache)},
                )
        # Other installer families are inventoried; this option never guesses their ownership.
        for site in self.home.glob(PATH_LOCAL_LIB_PYTHON_SITE_PACKAGES):
            for metadata in site.glob(PATH_DIST_INFO):
                if named(metadata.name):
                    self.finding(
                        metadata,
                        "Outside a venv; inspect original installer/OS ownership manually",
                        category=VALUE_REVIEW if self.remove_runtime_packages else TOKEN_PRESERVED,
                    )
        npm_roots = [
            self.home / PATH_LOCAL_LIB_NODE_MODULES,
            self.config_home / PATH_OPENCODE_NODE_MODULES,
            self.home / PATH_BUN_INSTALL_GLOBAL_NODE_MODULES,
        ]
        npm_roots += list((self.home / PATH_NPM_NPX).glob(PATH_NODE_MODULES))
        npm_roots += list((self.home / PATH_NVM_VERSIONS_NODE).glob(PATH_LIB_NODE_MODULES))
        if self.scope != USER_SCOPE:
            npm_roots.extend(
                [Path(PATH_USR_LOCAL_LIB_NODE_MODULES), Path(PATH_USR_LIB_NODE_MODULES)]
            )
        for root in npm_roots:
            for package in root.glob(PATH_PATTERN):
                if named(package.name):
                    self.finding(
                        package,
                        "Non-Python installer package retained; remove with its original package manager",
                        category=VALUE_REVIEW if self.remove_runtime_packages else TOKEN_PRESERVED,
                    )

    def launch_references(self):
        for root in (self.config_home / PATH_AUTOSTART, self.data_home / PATH_APPLICATIONS):
            if root.is_dir():
                for path in root.glob(PATH_DESKTOP):
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
                            owned_process({KEY_ARGS: shlex.split(command), KEY_CWD: str(root)})
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
                PATH_BASHRC,
                PATH_BASH_PROFILE,
                PATH_PROFILE,
                PATH_ZSHRC,
                PATH_ZPROFILE,
                PATH_PAM_ENVIRONMENT,
            )
        ]
        startup += list((self.config_home / PATH_ENVIRONMENT_D).glob(PATH_CONF))
        startup += list((self.config_home / PATH_FISH_CONF_D).glob(PATH_FISH))
        for path in startup:
            if not path.is_file() or backup_path(path):
                continue
            try:
                raw = path.read_bytes()
                lines = raw.decode().splitlines(keepends=True)
                removed, retained = [], []
                for number, line in enumerate(lines, 1):
                    stripped = line.strip()
                    env_line = re.match(SHELL_ASSIGNMENT_PATTERN, stripped)
                    own_alias = re.match(SHELL_ALIAS_PATTERN, stripped)
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
                            KEY_EDIT,
                            str(path),
                            "Remove standalone matching shell aliases/environment assignments",
                            {
                                KEY_LINES: removed,
                                KEY_RESOLVED: str(path.resolve()),
                                KEY_IDENTITY: fingerprint(path),
                            },
                            digest(raw),
                            "".join(retained),
                        )
                    )
            except (OSError, UnicodeError):
                self.finding(path, "Cannot read shell/environment configuration")

    def cron(self):
        """Read crontabs without installing a replacement during discovery."""
        if self.scope != KEY_SYSTEM:
            try:
                command = [
                    KEY_CRONTAB,
                    *(
                        [SHORT_OPTION_U, pwd.getpwuid(self.uid).pw_name]
                        if self.uid != os.getuid()
                        else []
                    ),
                    SHORT_OPTION_L,
                ]
                result = readonly(command)
                if result.returncode == 0:
                    after, removed, ambiguous = clean_cron(result.stdout, self.home)
                    if removed:
                        self.add(
                            Action(
                                KEY_CRONTAB,
                                str(self.uid),
                                "Remove matching user cron launches",
                                {KEY_UID: self.uid, KEY_LINES: removed},
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
        if self.scope != USER_SCOPE:
            paths = [Path(PATH_ETC_CRONTAB), *Path(PATH_ETC_CRON_D).glob(PATH_PATTERN)]
            for path in paths:
                if not path.is_file() or backup_path(path):
                    continue
                try:
                    raw = path.read_bytes()
                    after, removed, ambiguous = clean_cron(raw.decode(), self.home, system=True)
                    if removed:
                        self.add(
                            Action(
                                KEY_EDIT,
                                str(path),
                                "Remove matching system cron launches",
                                {
                                    KEY_LINES: removed,
                                    KEY_RESOLVED: str(path.resolve()),
                                    KEY_IDENTITY: fingerprint(path),
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
            self.protected.add((root / MODEL_CACHE_DIRECTORY).resolve())
            self.finding(
                root / MODEL_CACHE_DIRECTORY,
                "Downloaded models always retained, including with --remove-all",
                category=TOKEN_PRESERVED,
            )
            if not any(
                (root / marker).exists()
                for marker in (
                    PATH_STATE_SQLITE3,
                    PATH_EMBEDDING_CACHE_SQLITE3,
                    RUNTIMES_DIRECTORY,
                    MODEL_CACHE_DIRECTORY,
                    MERKLE_DIRECTORY,
                    KEY_PROJECTS,
                    TOKEN_INDEXES,
                )
            ):
                self.finding(root, "Storage path lacks recognized data markers; inspect manually")
                continue
            # Enumerate index artifacts individually. Never remove their storage parent/models.
            indexes = [root / name for name in (KEY_PROJECTS, TOKEN_INDEXES, MERKLE_DIRECTORY)]
            for name in (PATH_STATE_SQLITE3, PATH_EMBEDDING_CACHE_SQLITE3):
                indexes.extend(
                    root / (name + suffix) for suffix in ("", TOKEN_WAL, TOKEN_SHM, TOKEN_JOURNAL)
                )
            for path in indexes:
                if self.remove_indexes:
                    self.delete(
                        path,
                        "Remove project index, embedding cache or index statistics (--remove-indexes)",
                    )
                elif path.exists():
                    self.finding(
                        path, "Index retained; requires --remove-indexes", category=TOKEN_PRESERVED
                    )
        # Source roots discovered from later unit/installation records also protect earlier candidates.
        for key, action in list(self.actions.items()):
            if (
                action.kind == KEY_REMOVE
                and not action.details[KEY_SYMLINK]
                and self.protected_path(Path(action.target))
            ):
                self.finding(
                    action.target,
                    "Protected source/shared directory; removal excluded",
                    category=TOKEN_PRESERVED,
                )
                del self.actions[key]
        # A parent removal already handles children and config edits inside it.
        removals = [
            Path(a.target)
            for a in self.actions.values()
            if a.kind == KEY_REMOVE and not a.details[KEY_SYMLINK]
        ]
        actions = [
            a
            for a in self.actions.values()
            if a.kind not in {KEY_REMOVE, KEY_EDIT, INSTALL_MODE_PACKAGE}
            or not any(p in Path(a.target).parents for p in removals)
        ]
        order = {
            KEY_UNIT: 0,
            KEY_EDIT: 1,
            KEY_CRONTAB: 1,
            KEY_PROCESS: 2,
            INSTALL_MODE_PACKAGE: 3,
            KEY_REMOVE: 4,
        }
        actions.sort(
            key=lambda a: (
                bool(a.details.get(KEY_MATCHES))
                and all(
                    match[KEY_CATEGORY]
                    in {"cached MCP discovery entry", "marketplace catalog entry"}
                    for match in a.details[KEY_MATCHES]
                ),
                order[a.kind],
                0 if a.target.endswith((PATH_PATH, PATH_TIMER, PATH_SOCKET)) else 1,
                a.target,
            )
        )
        return actions

    def scan(self):
        self.app_state()
        self.units()
        for root in self.storage:
            self.protected.add((root / MODEL_CACHE_DIRECTORY).resolve())
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
        fields = stripped.split(
            None,
            (CRON_MACRO_FIELDS if stripped.startswith("@") else CRON_SCHEDULE_FIELDS) + int(system),
        )
        command = fields[-1]
        try:
            owned = not any(
                char in command for char in (";", "|", "&", "$(", "`", "\\", "%")
            ) and owned_process({KEY_ARGS: shlex.split(command), KEY_CWD: str(home)})
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
        text = (path / PATH_STAT).read_text()
        fields = text[text.rfind(")") + PROC_COMMAND_SEPARATOR_LENGTH :].split()
        return {
            KEY_PID: int(path.name),
            KEY_PPID: int(fields[PROC_PARENT_PID_INDEX]),
            KEY_STATE: fields[PROC_STATE_INDEX],
            KEY_START_TICKS: fields[PROC_START_TICKS_INDEX],
            KEY_UID: path.stat().st_uid,
            KEY_ARGS: [
                part.decode(errors=TOKEN_REPLACE)
                for part in (path / PATH_CMDLINE).read_bytes().split(b"\0")
                if part
            ],
            KEY_CWD: str((path / KEY_CWD).resolve()),
        }
    except (OSError, ValueError, IndexError):
        return None


def owned_process(info):
    args = info[KEY_ARGS]
    if not args or any(VALUE_CLEAN_EXISTING_INSTALLATIONS_AND_CONFIGS_PY in arg for arg in args):
        return False
    executable = Path(args[0]).name
    if named(executable):
        return True
    # Parse launch positions: prompts, `python -c`, pytest arguments and uv project paths
    # mentioning this repository must never identify an unrelated process as our server.
    remaining = args[1:]
    cwd = info[KEY_CWD]
    if executable == VALUE_UV:
        if VALUE_RUN not in remaining:
            return False
        remaining = remaining[remaining.index(VALUE_RUN) + 1 :]
    if executable in {VALUE_UV, TOKEN_UVX}:
        while remaining and remaining[0].startswith("-"):
            option = remaining.pop(0)
            if option in {
                OPTION_DIRECTORY,
                OPTION_PROJECT,
                OPTION_FROM,
                OPTION_WITH,
                OPTION_WITH_EDITABLE,
                OPTION_PYTHON,
                OPTION_INDEX,
                OPTION_INDEX_URL,
                OPTION_EXTRA_INDEX_URL,
            }:
                if not remaining:
                    return False
                value = remaining.pop(0)
                if option in {OPTION_DIRECTORY, OPTION_PROJECT}:
                    cwd = value
        return bool(remaining) and owned_process({KEY_ARGS: remaining, KEY_CWD: cwd})
    if executable.startswith(LANGUAGE_PYTHON):
        while remaining and remaining[0].startswith("-"):
            option = remaining.pop(0)
            if option == SHORT_OPTION_M:
                return bool(remaining and named(remaining[0]))
            if option not in {
                SHORT_OPTION_U,
                SHORT_OPTION_I,
                SHORT_OPTION_E,
                SHORT_OPTION_S,
                SHORT_OPTION_S_CASE_SENSITIVE,
                SHORT_OPTION_B,
                SHORT_OPTION_P,
            }:
                return False
        if not remaining:
            return False
        script = remaining[0]
        if named(Path(script).name):
            return True
        return script.endswith(
            (
                PATH_MCP_SERVER_SERVER_PY,
                PATH_CLAUDE_CONTEXT_LOCAL_SERVER_PY,
                PATH_CODE_SEARCH_LOCAL_SERVER_PY,
            )
        ) and (matches(cwd) or matches(script))
    if executable in {TOKEN_NODE, TOKEN_BUN} and remaining:
        script = remaining[0]
        return (
            not script.startswith("-")
            and script.endswith((PATH_JS, PATH_MJS, PATH_CJS))
            and matches(script)
        )
    return False


def unchanged(action):
    if action.kind in {KEY_REMOVE, KEY_EDIT}:
        path = Path(action.target)
        if not path.exists() and not path.is_symlink():
            return action.kind == KEY_REMOVE
        if fingerprint(path) != action.details[KEY_IDENTITY]:
            return False
        if action.kind == KEY_EDIT:
            return (
                str(path.resolve()) == action.details[KEY_RESOLVED]
                and digest(path.read_bytes()) == action.before
            )
        return str(path.parent.resolve()) == action.details[KEY_RESOLVED_PARENT]
    if action.kind == INSTALL_MODE_PACKAGE:
        path = Path(action.target)
        return (
            path.exists()
            and fingerprint(path) == action.details[KEY_IDENTITY]
            and str(path.resolve()) == action.details[KEY_RESOLVED]
            and all(
                Path(p).is_file() and digest(Path(p).read_bytes()) == expected
                for p, expected in action.details[KEY_EVIDENCE].items()
            )
        )
    return True


def systemctl(manager, scanner):
    if manager == KEY_SYSTEM:
        return [COMMAND_SYSTEMCTL]
    if os.getuid() == scanner.uid:
        return [COMMAND_SYSTEMCTL, OPTION_USER]
    user = pwd.getpwuid(scanner.uid).pw_name
    return [
        TOKEN_RUNUSER,
        SHORT_OPTION_U,
        user,
        TOKEN_,
        TOKEN_ENV,
        USER_RUNTIME_ENV_TEMPLATE.format(uid=scanner.uid),
        USER_DBUS_ENV_TEMPLATE.format(uid=scanner.uid),
        COMMAND_SYSTEMCTL,
        OPTION_USER,
    ]


def atomic_write(path, data, mode):
    fd, temporary = tempfile.mkstemp(prefix=PATH_CLEANUP, dir=path.parent)
    try:
        with os.fdopen(fd, TOKEN_WB) as stream:
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
        if action.kind in {KEY_EDIT, KEY_REMOVE, INSTALL_MODE_PACKAGE} and backup_path(
            action.target
        ):
            raise click.ClickException(f"Backup path is protected: {action.target}")
        if not unchanged(action):
            raise click.ClickException(f"Changed since discovery; rerun dry-run: {action.target}")
        if action.kind == INSTALL_MODE_PACKAGE and scanner.artifact_guard(
            Path(action.target), environment=True
        ):
            raise click.ClickException(f"Protected runtime cannot be uninstalled: {action.target}")
        if (
            action.kind == INSTALL_MODE_PACKAGE
            and action.details.get(KEY_CLEANUP_DIR)
            and scanner.artifact_guard(Path(action.details[KEY_CLEANUP_DIR]), environment=True)
        ):
            raise click.ClickException(
                f"Protected runtime directory: {action.details[KEY_CLEANUP_DIR]}"
            )
        if (
            action.kind == KEY_REMOVE
            and not Path(action.target).is_symlink()
            and scanner.artifact_guard(Path(action.target))
        ):
            raise click.ClickException(f"Artifact now contains protected data: {action.target}")
        if (
            action.kind == KEY_UNIT
            and action.details[KEY_MANAGER] == KEY_SYSTEM
            and os.geteuid() != 0
        ):
            raise click.ClickException(
                "System units require root. Review user-only --scope user or rerun as root with --home explicitly set."
            )
        if action.kind in {KEY_EDIT, KEY_REMOVE} and not os.access(
            Path(action.target).parent, os.W_OK
        ):
            raise click.ClickException(f"Insufficient write permission: {action.target}")
    backup.mkdir(parents=True, mode=PRIVATE_DIRECTORY_MODE, exist_ok=False)
    # Archive modified config files privately, outside all scanned harness locations.
    for index, action in enumerate(actions):
        if action.kind == KEY_EDIT:
            source = Path(action.target).resolve()
            atomic_write(
                backup / f"{index:04d}-{source.name}", source.read_bytes(), PRIVATE_FILE_MODE
            )
    atomic_write(
        backup / PATH_MANIFEST_JSON,
        json.dumps([a.public() for a in actions], indent=JSON_INDENT).encode(),
        PRIVATE_FILE_MODE,
    )
    units = [a for a in actions if a.kind == KEY_UNIT]
    for action in units:
        command = systemctl(action.details[KEY_MANAGER], scanner)
        # Stop activation first; static/transient units do not support enable/disable.
        state = readonly([*command, TOKEN_IS_ENABLED, action.details[KEY_UNIT]]).stdout.strip()
        if state in {
            TOKEN_ENABLED,
            TOKEN_ENABLED_RUNTIME,
            TOKEN_LINKED,
            TOKEN_LINKED_RUNTIME,
            TOKEN_ALIAS,
        }:
            subprocess.run([*command, COMMAND_DISABLE, action.details[KEY_UNIT]], check=True)
        subprocess.run(
            [*command, COMMAND_STOP, OPTION_NO_BLOCK, action.details[KEY_UNIT]], check=True
        )
    for action in actions:
        if action.kind == KEY_EDIT:
            if backup_path(action.target) or not unchanged(action):
                raise click.ClickException(
                    f"Config changed during cleanup; saved backup: {action.target}"
                )
            path = Path(action.target).resolve()
            info = path.stat()
            atomic_write(
                path, action.after.encode(), stat.S_IMODE(info.st_mode) & PRIVATE_FILE_MODE
            )
            if os.geteuid() == 0:
                os.chown(path, info.st_uid, info.st_gid)
        elif action.kind == KEY_CRONTAB:
            command = [
                KEY_CRONTAB,
                *(
                    [SHORT_OPTION_U, pwd.getpwuid(scanner.uid).pw_name]
                    if scanner.uid != os.getuid()
                    else []
                ),
            ]
            current = readonly([*command, SHORT_OPTION_L])
            if current.returncode or digest(current.stdout.encode()) != action.before:
                raise click.ClickException("Crontab changed since discovery; refusing replacement")
            atomic_write(backup / PATH_CRONTAB_TXT, current.stdout.encode(), PRIVATE_FILE_MODE)
            subprocess.run([*command, "-"], input=action.after, text=True, check=True)
    processes = [a for a in actions if a.kind == KEY_PROCESS]

    def alive(action):
        current = process_info(Path(PATH_PROC) / action.target)
        return (
            current
            and current[KEY_STATE] not in DEAD_PROCESS_STATES
            and current[KEY_UID] == action.details[KEY_UID]
            and current[KEY_START_TICKS] == action.details[KEY_START_TICKS]
        )

    for sig in (signal.SIGTERM, signal.SIGKILL):
        for action in processes:
            if alive(action):
                try:
                    os.kill(action.details[KEY_PID], sig)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + (
            grace if sig == signal.SIGTERM else FORCED_EXIT_TIMEOUT_SECONDS
        )
        while any(alive(a) for a in processes) and time.monotonic() < deadline:
            time.sleep(PROCESS_POLL_SECONDS)
    if any(alive(a) for a in processes):
        raise click.ClickException("Some server processes remain; refusing to delete installations")
    scanner.processes()
    if any(alive(action) for action in scanner.actions.values() if action.kind == KEY_PROCESS):
        raise click.ClickException(
            "A harness restarted a server; close the harness and rerun the dry-run before cleanup"
        )
    for action in units:
        result = readonly(
            [
                *systemctl(action.details[KEY_MANAGER], scanner),
                TOKEN_IS_ACTIVE,
                action.details[KEY_UNIT],
            ]
        )
        if result.stdout.strip() in {
            TOKEN_ACTIVE,
            TOKEN_ACTIVATING,
            TOKEN_DEACTIVATING,
            TOKEN_RELOADING,
        }:
            raise click.ClickException(f"Unit has not stopped: {action.target}; files retained")
    for action in actions:
        if action.kind == INSTALL_MODE_PACKAGE:
            if not unchanged(action) or scanner.artifact_guard(
                Path(action.target), environment=True
            ):
                raise click.ClickException(f"Runtime ownership/protection changed: {action.target}")
            if action.details.get(KEY_CLEANUP_DIR) and scanner.artifact_guard(
                Path(action.details[KEY_CLEANUP_DIR]), environment=True
            ):
                raise click.ClickException(
                    f"Runtime directory now contains protected data: {action.details[KEY_CLEANUP_DIR]}"
                )
            for command in action.details[KEY_COMMANDS]:
                overrides = {ENV_HOME: str(scanner.home), **action.details[KEY_ENVIRONMENT]}
                if scanner.uid != os.getuid():
                    command = [
                        TOKEN_RUNUSER,
                        SHORT_OPTION_U,
                        pwd.getpwuid(scanner.uid).pw_name,
                        TOKEN_,
                        TOKEN_ENV,
                        *[f"{key}={value}" for key, value in overrides.items()],
                        *command,
                    ]
                subprocess.run(
                    command, env={**os.environ, **overrides}, check=True, cwd=scanner.home
                )
            if action.details.get(KEY_CLEANUP_DIR):
                # Shared venvs stay. A verified generated runtime loses its empty package environment
                # and provisioning metadata only after every original-installer uninstall succeeded.
                path = Path(action.details[KEY_CLEANUP_DIR])
                if fingerprint(path) != action.details[
                    KEY_CLEANUP_IDENTITY
                ] or scanner.artifact_guard(path, environment=True):
                    raise click.ClickException(
                        f"Managed runtime changed/protected; directory retained: {path}"
                    )
                shutil.rmtree(path)
        elif action.kind == KEY_REMOVE:
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
    for manager in {a.details[KEY_MANAGER] for a in units}:
        subprocess.run([*systemctl(manager, scanner), COMMAND_DAEMON_RELOAD], check=True)
    click.echo(f"Cleanup applied. Private configuration backups: {backup}")
    if any(item[KEY_CATEGORY] == VALUE_REVIEW for item in scanner.findings):
        raise click.ClickException(
            "Known installations removed; reported references still require manual review"
        )


@click.command(context_settings={KEY_MAX_CONTENT_WIDTH: CLI_MAX_CONTENT_WIDTH})
@click.option(
    OPTION_DRY_RUN,
    is_flag=True,
    help="Read-only discovery and report. Creates no backups and changes nothing.",
)
@click.option(
    OPTION_APPLY,
    is_flag=True,
    help="Perform cleanup only after you have personally reviewed this script.",
)
@click.option(
    OPTION_REVIEWED,
    is_flag=True,
    help="Required with --apply; acknowledges personal review of the script.",
)
@click.option(
    OPTION_HOME,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=lambda: str(Path.home()),
    show_default="current user's home",
    help="Home directory of the user whose installations, processes and harness configurations to inspect.",
)
@click.option(
    OPTION_SCOPE,
    type=click.Choice([USER_SCOPE, KEY_SYSTEM, HARNESS_ALL]),
    default=HARNESS_ALL,
    show_default=True,
    help="Which systemd/launcher scopes to inventory. Harnesses belong to --home.",
)
@click.option(
    OPTION_PROJECT_ROOT,
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Additional workspace with project-local agent configs; repeat as needed.",
)
@click.option(
    OPTION_SCAN_ROOT,
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Additional directory of harness configurations to scan recursively.",
)
@click.option(
    OPTION_REMOVE_INDEXES,
    is_flag=True,
    help="Remove project indexes, embedding caches and index statistics. Always retain models.",
)
@click.option(
    OPTION_REMOVE_RUNTIME_PACKAGES,
    is_flag=True,
    help="Uninstall runtime/CLI packages with their original installer; never source-worktree environments.",
)
@click.option(
    OPTION_REMOVE_ALL,
    is_flag=True,
    help="Enable --remove-indexes and --remove-runtime-packages. Models and source environments are still preserved.",
)
@click.option(
    OPTION_JSON,
    CLI_DESTINATION_JSON,
    is_flag=True,
    help="Emit the redacted dry-run inventory as JSON.",
)
@click.option(
    OPTION_BACKUP_DIR,
    type=click.Path(path_type=Path),
    help="New private backup directory for --apply; never written during --dry-run.",
)
@click.option(
    OPTION_GRACE_SECONDS,
    type=click.IntRange(MIN_GRACE_SECONDS, MAX_GRACE_SECONDS),
    default=DEFAULT_GRACE_SECONDS,
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
    if sys.platform != VALUE_LINUX:
        raise click.ClickException("This cleanup script supports Linux systemd installations")
    if os.geteuid() == 0 and os.environ.get(ENV_SUDO_USER) and home == Path.home():
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
        KEY_DRY_RUN: dry_run,
        KEY_HOME: str(home),
        KEY_SCOPE: scope,
        KEY_REMOVE_INDEXES: remove_indexes,
        KEY_REMOVE_RUNTIME_PACKAGES: remove_runtime_packages,
        KEY_REMOVE_ALL: remove_all,
        KEY_MODELS_PRESERVED: True,
        KEY_COUNTS: dict(Counter(a.kind for a in actions)),
        KEY_ACTIONS: [a.public() for a in actions],
        KEY_FINDINGS: scanner.findings,
        KEY_CONFIG_FILES_EXAMINED: len(scanner.scanned),
    }
    if as_json:
        click.echo(json.dumps(report, indent=JSON_INDENT))
    else:
        click.echo("DRY RUN — no changes" if dry_run else "REVIEWED CLEANUP PLAN")
        click.echo(f"Planned actions: {len(actions)}; counts: {report[KEY_COUNTS]}")
        for action in actions:
            public = action.public()
            click.echo(f"{action.kind.upper():8} {public[KEY_TARGET]}\n         {action.reason}")
            for command in public.get(KEY_COMMANDS, []):
                click.echo(f"         command: {shlex.join(command)}")
            for match in public.get(KEY_MATCHES, []):
                fields = "; ".join(
                    f"{field[KEY_FIELD]}: {field.get(KEY_MATCHED_NAME, field.get(KEY_MATCH))}"
                    for field in match[KEY_MATCHED_FIELDS]
                )
                click.echo(f"         {match[KEY_ENTRY]} ({fields})")
            if not public.get(KEY_MATCHES):
                for entry in public.get(KEY_ENTRIES, []):
                    click.echo(f"         entry: {entry}")
            if public.get(KEY_LINES):
                click.echo(f"         lines: {', '.join(map(str, public[KEY_LINES]))}")
        for item in scanner.findings:
            click.echo(
                f"{item[KEY_CATEGORY].upper():8} {item[KEY_PATH]}\n         {item[KEY_REASON]}"
            )
    if dry_run:
        return
    if not sys.stdin.isatty():
        raise click.ClickException("Real cleanup requires interactive personal confirmation")
    answer = click.prompt("After reviewing the script and plan, type REMOVE BOTH INSTALLATIONS")
    if answer != "REMOVE BOTH INSTALLATIONS":
        raise click.ClickException("Confirmation did not match; no changes made")
    backup = backup_dir or home / PATH_LOCAL_STATE_MCP_CLEANUP_BACKUPS / time.strftime(
        BACKUP_TIMESTAMP_FORMAT
    )
    if any(
        Path(a.target) == backup or Path(a.target) in backup.parents
        for a in actions
        if a.kind == KEY_REMOVE
    ):
        raise click.ClickException("Backup directory cannot be inside a removal target")
    apply_plan(scanner, actions, backup, grace_seconds)


if __name__ == "__main__":
    main()
