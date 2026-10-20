"""User-scoped MCP registration and removal of this plugin's own harness entries."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import json5
import tomlkit

from code_search_local import constants

from .storage import atomic_text

NAME = "code-search-local"
HARNESSES = ("codex", "claude", "opencode")


def selection(values=()):
    values = set(values or (constants.HARNESS_NONE,))
    if not values <= {*HARNESSES, constants.HARNESS_ALL, constants.HARNESS_NONE}:
        raise ValueError("Unknown agent harness")
    if constants.HARNESS_NONE in values and len(values) > 1:
        raise ValueError("--agent-harness none cannot be combined with another harness")
    return tuple(name for name in HARNESSES if constants.HARNESS_ALL in values or name in values)


def targets(names=HARNESSES):
    result = []
    for name in names:
        if name == constants.HARNESS_CODEX:
            root = Path(
                os.environ.get(constants.ENV_CODEX_HOME, Path.home() / constants.PATH_CODEX)
            )
            configs = [root / constants.PATH_CONFIG_TOML]
        elif name == constants.HARNESS_CLAUDE:
            root = Path(
                os.environ.get(constants.ENV_CLAUDE_CONFIG_DIR, Path.home() / constants.PATH_CLAUDE)
            )
            configs = [
                root / constants.PATH_CLAUDE_JSON
                if constants.ENV_CLAUDE_CONFIG_DIR in os.environ
                else Path.home() / constants.PATH_CLAUDE_JSON
            ]
        else:
            root = (
                Path(
                    os.environ.get(
                        constants.ENV_XDG_CONFIG_HOME, Path.home() / constants.PATH_CONFIG
                    )
                )
                / constants.HARNESS_OPENCODE
            )
            configs = [
                root / constants.PATH_OPENCODE_JSON,
                root / constants.OPENCODE_JSONC_FILENAME,
            ]
            if os.environ.get(constants.ENV_OPENCODE_CONFIG_DIR):
                root = Path(os.environ[constants.ENV_OPENCODE_CONFIG_DIR])
                configs += [
                    root / constants.PATH_OPENCODE_JSON,
                    root / constants.OPENCODE_JSONC_FILENAME,
                ]
            if os.environ.get(constants.ENV_OPENCODE_CONFIG):
                configs.append(Path(os.environ[constants.ENV_OPENCODE_CONFIG]))
        configs = list(dict.fromkeys(str(path.expanduser().absolute()) for path in configs))
        primary = next((path for path in reversed(configs) if Path(path).exists()), configs[0])
        if name == constants.HARNESS_OPENCODE:
            if constants.ENV_OPENCODE_CONFIG_DIR in os.environ and not any(
                Path(p).exists() for p in configs
            ):
                primary = str(root / constants.PATH_OPENCODE_JSON)
            primary = os.environ.get(constants.ENV_OPENCODE_CONFIG, primary)
        result.append(
            {
                constants.KEY_NAME: name,
                constants.KEY_ROOT: str(root.expanduser().absolute()),
                constants.KEY_CONFIGS: configs,
                constants.KEY_PRIMARY: str(Path(primary).expanduser().absolute()),
            }
        )
    return result


def read_document(path):
    path = Path(path)
    if not path.exists():
        return tomlkit.document() if path.suffix == constants.PATH_TOML else {}
    text = path.read_text()
    document = tomlkit.parse(text) if path.suffix == constants.PATH_TOML else json5.loads(text)
    if not isinstance(document, dict):
        raise ValueError(f"Harness configuration must be an object: {path}")
    return document


def save_document(path, document, *, backup=True):
    path = Path(path)
    text = (
        tomlkit.dumps(document)
        if path.suffix == constants.PATH_TOML
        else json.dumps(document, indent=constants.JSON_INDENT) + "\n"
    )
    if path.exists():
        previous = path.read_text()
        if previous == text:
            return
        if backup:
            atomic_text(path.with_name(path.name + constants.PATH_CODE_SEARCH_LOCAL_BAK), previous)
    atomic_text(path, text)


def plugin_id(value):
    return isinstance(value, str) and (value == NAME or value.startswith(NAME + "@"))


def plugins(target):
    root = Path(target[constants.KEY_ROOT])
    if target[constants.KEY_NAME] == constants.HARNESS_CLAUDE:
        registry = read_document(root / constants.PATH_PLUGINS_INSTALLED_PLUGINS_JSON)
        return [
            key
            for key, entries in registry.get(constants.KEY_PLUGINS, {}).items()
            if plugin_id(key)
            and any(entry.get(constants.KEY_SCOPE) == constants.USER_SCOPE for entry in entries)
        ]
    if target[constants.KEY_NAME] == constants.HARNESS_CODEX:
        return [
            key
            for key in read_document(target[constants.KEY_PRIMARY]).get(constants.KEY_PLUGINS, {})
            if plugin_id(key)
        ]
    return [
        item
        for path in target[constants.KEY_CONFIGS]
        for item in read_document(path).get(constants.KEY_PLUGIN, [])
        if plugin_id(item)
    ]


def command_env(target):
    env = os.environ.copy()
    if target[constants.KEY_NAME] == constants.HARNESS_CODEX:
        env[constants.ENV_CODEX_HOME] = target[constants.KEY_ROOT]
    elif target[constants.KEY_NAME] == constants.HARNESS_CLAUDE:
        if (
            Path(target[constants.KEY_PRIMARY])
            == Path(target[constants.KEY_ROOT]) / constants.PATH_CLAUDE_JSON
        ):
            env[constants.ENV_CLAUDE_CONFIG_DIR] = target[constants.KEY_ROOT]
        else:
            env.pop(constants.ENV_CLAUDE_CONFIG_DIR, None)
    return env


def remove_plugins(target):
    installed = plugins(target)
    tool = target[constants.KEY_NAME]
    if (
        tool in (constants.HARNESS_CLAUDE, constants.HARNESS_CODEX)
        and installed
        and shutil.which(tool)
    ):
        for identifier in installed:
            args = (
                [
                    tool,
                    constants.KEY_PLUGIN,
                    constants.COMMAND_UNINSTALL,
                    identifier,
                    constants.OPTION_SCOPE,
                    constants.USER_SCOPE,
                    constants.OPTION_KEEP_DATA,
                ]
                if tool == constants.HARNESS_CLAUDE
                else [
                    tool,
                    constants.KEY_PLUGIN,
                    constants.COMMAND_REMOVE,
                    identifier,
                    constants.OPTION_JSON,
                ]
            )
            subprocess.run(
                args,
                env=command_env(target),
                check=True,
                capture_output=True,
                text=True,
                timeout=constants.NATIVE_HARNESS_TIMEOUT_SECONDS,
            )
    elif tool == constants.HARNESS_CLAUDE and installed:
        # Config cleanup still works if the harness executable has been removed.
        path = Path(target[constants.KEY_ROOT]) / constants.PATH_PLUGINS_INSTALLED_PLUGINS_JSON
        registry = read_document(path)
        for identifier in installed:
            entries = [
                entry
                for entry in registry[constants.KEY_PLUGINS][identifier]
                if entry.get(constants.KEY_SCOPE) != constants.USER_SCOPE
            ]
            if entries:
                registry[constants.KEY_PLUGINS][identifier] = entries
            else:
                del registry[constants.KEY_PLUGINS][identifier]
        save_document(path, registry)
    # Remove stale enablement even if no cached installation remains.
    if tool == constants.HARNESS_CLAUDE:
        path = Path(target[constants.KEY_ROOT]) / constants.PATH_SETTINGS_JSON
        doc = read_document(path)
        enabled = doc.get(constants.KEY_ENABLED_PLUGINS, {})
        keys = [key for key in enabled if plugin_id(key)]
        for key in keys:
            del enabled[key]
        if keys:
            save_document(path, doc)
    return installed


def unregister(target, *, remove_plugin=True, backup=True):
    removed = remove_plugins(target) if remove_plugin else []
    key = {
        constants.HARNESS_CODEX: constants.KEY_MCP_SERVERS_LOWERCASE,
        constants.HARNESS_CLAUDE: constants.KEY_MCP_SERVERS,
        constants.HARNESS_OPENCODE: constants.KEY_MCP,
    }[target[constants.KEY_NAME]]
    for path in target[constants.KEY_CONFIGS]:
        doc = read_document(path)
        changed = NAME in doc.get(key, {})
        doc.get(key, {}).pop(NAME, None)
        if remove_plugin and target[constants.KEY_NAME] == constants.HARNESS_CODEX:
            for identifier in list(doc.get(constants.KEY_PLUGINS, {})):
                if plugin_id(identifier):
                    del doc[constants.KEY_PLUGINS][identifier]
                    changed = True
        if remove_plugin and target[constants.KEY_NAME] == constants.HARNESS_OPENCODE:
            entries = doc.get(constants.KEY_PLUGIN, [])
            remaining = [entry for entry in entries if not plugin_id(entry)]
            if remaining != entries:
                doc[constants.KEY_PLUGIN] = remaining
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
    endpoint = settings.url + constants.MCP_ENDPOINT
    for target in selected:
        originals = {
            Path(path): Path(path).read_text() if Path(path).exists() else None
            for path in target[constants.KEY_CONFIGS]
        }
        for path, original in originals.items():
            if original is not None:
                atomic_text(
                    path.with_name(path.name + constants.PATH_CODE_SEARCH_LOCAL_BAK), original
                )
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
    path = target[constants.KEY_PRIMARY]
    doc = read_document(path)
    if target[constants.KEY_NAME] == constants.HARNESS_CODEX:
        key, entry = (
            constants.KEY_MCP_SERVERS_LOWERCASE,
            {
                constants.KEY_URL: endpoint,
                constants.KEY_HTTP_HEADERS: {constants.KEY_AUTHORIZATION: f"Bearer {token}"},
            },
        )
    elif target[constants.KEY_NAME] == constants.HARNESS_CLAUDE:
        key, entry = (
            constants.KEY_MCP_SERVERS,
            {
                constants.KEY_TYPE: constants.TRANSPORT_HTTP,
                constants.KEY_URL: endpoint,
                constants.KEY_HEADERS: {constants.KEY_AUTHORIZATION: f"Bearer {token}"},
            },
        )
    else:
        key, entry = (
            constants.KEY_MCP,
            {
                constants.KEY_TYPE: constants.OPENCODE_TRANSPORT_REMOTE,
                constants.KEY_URL: endpoint,
                constants.KEY_ENABLED: True,
                constants.KEY_OAUTH: False,
                constants.KEY_HEADERS: {constants.KEY_AUTHORIZATION: f"Bearer {token}"},
            },
        )
    doc.setdefault(key, {})[NAME] = entry
    save_document(path, doc, backup=False)
