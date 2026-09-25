"""User-scoped MCP registration and removal of this plugin's own harness entries."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import json5
import tomlkit

from .storage import atomic_text

NAME = "code-search-local"
HARNESSES = ("codex", "claude", "opencode")


def selection(values=()):
    values = set(values or ("none",))
    if not values <= {*HARNESSES, "all", "none"}:
        raise ValueError("Unknown agent harness")
    if "none" in values and len(values) > 1:
        raise ValueError("--agent-harness none cannot be combined with another harness")
    return tuple(name for name in HARNESSES if "all" in values or name in values)


def targets(names=HARNESSES):
    result = []
    for name in names:
        if name == "codex":
            root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
            configs = [root / "config.toml"]
        elif name == "claude":
            root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
            configs = [
                root / ".claude.json"
                if "CLAUDE_CONFIG_DIR" in os.environ
                else Path.home() / ".claude.json"
            ]
        else:
            root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode"
            configs = [root / "opencode.json", root / "opencode.jsonc"]
            if os.environ.get("OPENCODE_CONFIG_DIR"):
                root = Path(os.environ["OPENCODE_CONFIG_DIR"])
                configs += [root / "opencode.json", root / "opencode.jsonc"]
            if os.environ.get("OPENCODE_CONFIG"):
                configs.append(Path(os.environ["OPENCODE_CONFIG"]))
        configs = list(dict.fromkeys(str(path.expanduser().absolute()) for path in configs))
        primary = next((path for path in reversed(configs) if Path(path).exists()), configs[0])
        if name == "opencode":
            if "OPENCODE_CONFIG_DIR" in os.environ and not any(Path(p).exists() for p in configs):
                primary = str(root / "opencode.json")
            primary = os.environ.get("OPENCODE_CONFIG", primary)
        result.append(
            {
                "name": name,
                "root": str(root.expanduser().absolute()),
                "configs": configs,
                "primary": str(Path(primary).expanduser().absolute()),
            }
        )
    return result


def read_document(path):
    path = Path(path)
    if not path.exists():
        return tomlkit.document() if path.suffix == ".toml" else {}
    text = path.read_text()
    document = tomlkit.parse(text) if path.suffix == ".toml" else json5.loads(text)
    if not isinstance(document, dict):
        raise ValueError(f"Harness configuration must be an object: {path}")
    return document


def save_document(path, document, *, backup=True):
    path = Path(path)
    text = (
        tomlkit.dumps(document) if path.suffix == ".toml" else json.dumps(document, indent=2) + "\n"
    )
    if path.exists():
        previous = path.read_text()
        if previous == text:
            return
        if backup:
            atomic_text(path.with_name(path.name + ".code-search-local.bak"), previous)
    atomic_text(path, text)


def plugin_id(value):
    return isinstance(value, str) and (value == NAME or value.startswith(NAME + "@"))


def plugins(target):
    root = Path(target["root"])
    if target["name"] == "claude":
        registry = read_document(root / "plugins/installed_plugins.json")
        return [
            key
            for key, entries in registry.get("plugins", {}).items()
            if plugin_id(key) and any(entry.get("scope") == "user" for entry in entries)
        ]
    if target["name"] == "codex":
        return [
            key for key in read_document(target["primary"]).get("plugins", {}) if plugin_id(key)
        ]
    return [
        item
        for path in target["configs"]
        for item in read_document(path).get("plugin", [])
        if plugin_id(item)
    ]


def command_env(target):
    env = os.environ.copy()
    if target["name"] == "codex":
        env["CODEX_HOME"] = target["root"]
    elif target["name"] == "claude":
        if Path(target["primary"]) == Path(target["root"]) / ".claude.json":
            env["CLAUDE_CONFIG_DIR"] = target["root"]
        else:
            env.pop("CLAUDE_CONFIG_DIR", None)
    return env


def remove_plugins(target):
    installed = plugins(target)
    tool = target["name"]
    if tool in ("claude", "codex") and installed and shutil.which(tool):
        for identifier in installed:
            args = (
                [tool, "plugin", "uninstall", identifier, "--scope", "user", "--keep-data"]
                if tool == "claude"
                else [tool, "plugin", "remove", identifier, "--json"]
            )
            subprocess.run(
                args,
                env=command_env(target),
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
    elif tool == "claude" and installed:
        # Config cleanup still works if the harness executable has been removed.
        path = Path(target["root"]) / "plugins/installed_plugins.json"
        registry = read_document(path)
        for identifier in installed:
            entries = [
                entry for entry in registry["plugins"][identifier] if entry.get("scope") != "user"
            ]
            if entries:
                registry["plugins"][identifier] = entries
            else:
                del registry["plugins"][identifier]
        save_document(path, registry)
    # Remove stale enablement even if no cached installation remains.
    if tool == "claude":
        path = Path(target["root"]) / "settings.json"
        doc = read_document(path)
        enabled = doc.get("enabledPlugins", {})
        keys = [key for key in enabled if plugin_id(key)]
        for key in keys:
            del enabled[key]
        if keys:
            save_document(path, doc)
    return installed


def unregister(target, *, remove_plugin=True, backup=True):
    removed = remove_plugins(target) if remove_plugin else []
    key = {"codex": "mcp_servers", "claude": "mcpServers", "opencode": "mcp"}[target["name"]]
    for path in target["configs"]:
        doc = read_document(path)
        changed = NAME in doc.get(key, {})
        doc.get(key, {}).pop(NAME, None)
        if remove_plugin and target["name"] == "codex":
            for identifier in list(doc.get("plugins", {})):
                if plugin_id(identifier):
                    del doc["plugins"][identifier]
                    changed = True
        if remove_plugin and target["name"] == "opencode":
            entries = doc.get("plugin", [])
            remaining = [entry for entry in entries if not plugin_id(entry)]
            if remaining != entries:
                doc["plugin"] = remaining
                changed = True
        if changed:
            save_document(path, doc, backup=backup)
            removed.append(str(path))
    return removed


def register(settings, selected, *, marketplace=False):
    from .service import token_for

    if not selected:
        return
    token = token_for(settings.root)
    endpoint = settings.url + "/mcp"
    for target in selected:
        originals = {
            Path(path): Path(path).read_text() if Path(path).exists() else None
            for path in target["configs"]
        }
        for path, original in originals.items():
            if original is not None:
                atomic_text(path.with_name(path.name + ".code-search-local.bak"), original)
        try:
            _register(target, endpoint, token, marketplace=marketplace)
        except (OSError, ValueError, subprocess.SubprocessError):
            # Restore MCP configuration. Native plugin removal itself is not reversible here.
            for path, original in originals.items():
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_text(path, original)
            raise


def _register(target, endpoint, token, *, marketplace):
    # Replacing the entire entry drops stale stdio commands and transport options.
    unregister(target, remove_plugin=not marketplace, backup=False)
    path = target["primary"]
    doc = read_document(path)
    if target["name"] == "codex":
        key, entry = (
            "mcp_servers",
            {"url": endpoint, "http_headers": {"Authorization": f"Bearer {token}"}},
        )
    elif target["name"] == "claude":
        key, entry = (
            "mcpServers",
            {"type": "http", "url": endpoint, "headers": {"Authorization": f"Bearer {token}"}},
        )
    else:
        key, entry = (
            "mcp",
            {
                "type": "remote",
                "url": endpoint,
                "enabled": True,
                "oauth": False,
                "headers": {"Authorization": f"Bearer {token}"},
            },
        )
    doc.setdefault(key, {})[NAME] = entry
    save_document(path, doc, backup=False)
