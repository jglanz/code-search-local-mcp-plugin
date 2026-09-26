"""Installation records and systemd cleanup after native marketplace removal."""

import json
import subprocess
from pathlib import Path

from code_search_local import constants

from . import harnesses
from .config import config_path
from .storage import ServiceLock, atomic_json, atomic_text


def state_path():
    return config_path().with_name(constants.PATH_INSTALLATION_JSON)


def load_state():
    return json.loads(state_path().read_text()) if state_path().exists() else {}


def merge_targets(*groups):
    return list(
        {
            (item[constants.KEY_NAME], item[constants.KEY_PRIMARY]): item
            for group in groups
            for item in group
        }.values()
    )


def marketplace_entries(selected):
    entries = []
    for target in selected:
        if target[constants.KEY_NAME] in (constants.HARNESS_CLAUDE, constants.HARNESS_CODEX):
            entries.extend(
                {constants.KEY_TARGET: target, constants.KEY_PLUGIN: identifier}
                for identifier in harnesses.plugins(target)
            )
    if not entries:
        raise ValueError(
            "--marketplace requires an installed plugin in a selected Claude/Codex harness"
        )
    return entries


def guard_paths(unit):
    stem = unit.stem + constants.MARKETPLACE_UNIT_SUFFIX
    return [
        unit.with_name(stem + suffix)
        for suffix in (constants.PATH_PATH, constants.PATH_TIMER, constants.PATH_SERVICE)
    ]


def remove_guard(unit):
    from .install import run

    paths = guard_paths(unit)
    for path in paths[:2]:
        if path.exists():
            run(
                [
                    constants.COMMAND_SYSTEMCTL,
                    constants.OPTION_USER,
                    constants.COMMAND_DISABLE,
                    constants.OPTION_NOW,
                    path.name,
                ]
            )
    for path in paths:
        path.unlink(missing_ok=True)


def record_installation(result, selected, entries, python):
    previous = load_state()
    state = {
        **result,
        constants.KEY_PYTHON: str(python),
        constants.KEY_TARGETS: merge_targets(previous.get(constants.KEY_TARGETS, []), selected),
        constants.KEY_MARKETPLACE: [],
    }
    if entries:
        retained = []
        for entry in previous.get(constants.KEY_MARKETPLACE, []):
            try:
                if entry[constants.KEY_PLUGIN] not in harnesses.plugins(
                    entry[constants.KEY_TARGET]
                ):
                    continue
            except (OSError, ValueError):
                # Preserve an unreadable profile for the watcher's later retry.
                pass
            retained.append(entry)
        combined = [*retained, *entries]
        state[constants.KEY_MARKETPLACE] = list(
            {
                (
                    e[constants.KEY_TARGET][constants.KEY_NAME],
                    e[constants.KEY_TARGET][constants.KEY_PRIMARY],
                    e[constants.KEY_PLUGIN],
                ): e
                for e in combined
            }.values()
        )
    atomic_json(state_path(), state)
    install_guard(state)


def install_guard(state):
    from .install import run, systemd_quote

    unit = Path(state[constants.KEY_SERVICE])
    remove_guard(unit)
    if not state[constants.KEY_MARKETPLACE]:
        run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD])
        return
    path_unit, timer_unit, service_unit = guard_paths(unit)
    watches = set()
    for entry in state[constants.KEY_MARKETPLACE]:
        target = entry[constants.KEY_TARGET]
        watches.add(
            str(Path(target[constants.KEY_ROOT]) / constants.PATH_PLUGINS_INSTALLED_PLUGINS_JSON)
            if target[constants.KEY_NAME] == constants.HARNESS_CLAUDE
            else target[constants.KEY_PRIMARY]
        )
    if any("\n" in path or "\r" in path for path in watches):
        raise ValueError("Harness config paths cannot contain line breaks")
    watches_text = "".join(
        constants.SYSTEMD_PATH_CHANGED_PREFIX + p.replace("%", "%%") + "\n" for p in sorted(watches)
    )
    atomic_text(
        path_unit,
        constants.MARKETPLACE_PATH_UNIT_TEMPLATE.format(
            watches=watches_text, service=service_unit.name
        ),
    )
    atomic_text(
        timer_unit, constants.MARKETPLACE_TIMER_UNIT_TEMPLATE.format(service=service_unit.name)
    )
    command = " ".join(
        systemd_quote(x)
        for x in (
            state[constants.KEY_PYTHON],
            constants.SHORT_OPTION_M,
            constants.PACKAGE_NAME,
            constants.COMMAND_MARKETPLACE_CHECK,
        )
    )
    environment = systemd_quote(
        constants.XDG_CONFIG_ASSIGNMENT_PREFIX + str(config_path().parent.parent),
        expand_dollars=False,
    )
    atomic_text(
        service_unit,
        constants.MARKETPLACE_SERVICE_UNIT_TEMPLATE.format(
            command=command, environment=environment
        ),
    )
    run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD])
    run(
        [
            constants.COMMAND_SYSTEMCTL,
            constants.OPTION_USER,
            constants.COMMAND_ENABLE,
            constants.OPTION_NOW,
            path_unit.name,
            timer_unit.name,
        ]
    )


def uninstall(*, remove_plugins=True, locked=False, discover=True):
    from .install import run, unit_path

    lock = None if locked else ServiceLock(config_path().parent, constants.PATH_INSTALL_LOCK)
    try:
        state = load_state()
        unit = Path(state.get(constants.KEY_SERVICE, unit_path()))
        if unit.exists():
            run(
                [
                    constants.COMMAND_SYSTEMCTL,
                    constants.OPTION_USER,
                    constants.COMMAND_DISABLE,
                    constants.OPTION_NOW,
                    unit.name,
                ]
            )
            unit.unlink()
        run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD])
        removed, errors = [], []
        for target in merge_targets(
            state.get(constants.KEY_TARGETS, []), harnesses.targets() if discover else []
        ):
            try:
                removed.extend(harnesses.unregister(target, remove_plugin=remove_plugins))
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                errors.append(f"{target[constants.KEY_NAME]}: {error}")
        if errors:
            raise RuntimeError("Service removed; harness cleanup needs retry: " + "; ".join(errors))
        # Keep the timer available until all cleanup succeeds, so transient config errors retry.
        remove_guard(unit)
        run([constants.COMMAND_SYSTEMCTL, constants.OPTION_USER, constants.COMMAND_DAEMON_RELOAD])
        state_path().unlink(missing_ok=True)
        return {
            constants.KEY_SERVICE_REMOVED: str(unit),
            constants.KEY_UNREGISTERED: removed,
            constants.KEY_DATA_PRESERVED: True,
        }
    finally:
        if lock is not None:
            lock.close()


def marketplace_check():
    import time

    try:
        lock = ServiceLock(config_path().parent, constants.PATH_INSTALL_LOCK)
    except RuntimeError:
        return {constants.KEY_STATUS: constants.STATUS_BUSY}
    try:
        state = load_state()
        entries = state.get(constants.KEY_MARKETPLACE, [])
        try:
            missing = [
                entry
                for entry in entries
                if entry[constants.KEY_PLUGIN] not in harnesses.plugins(entry[constants.KEY_TARGET])
            ]
        except (OSError, ValueError):
            return {constants.KEY_STATUS: constants.STATUS_RETRY}
        if not missing:
            return {constants.KEY_STATUS: constants.STATUS_INSTALLED}
        # Registry writes during upgrades can briefly remove an entry. Require two observations.
        time.sleep(constants.MARKETPLACE_RETRY_DELAY_SECONDS)
        try:
            if not any(
                entry[constants.KEY_PLUGIN] not in harnesses.plugins(entry[constants.KEY_TARGET])
                for entry in missing
            ):
                return {constants.KEY_STATUS: constants.STATUS_INSTALLED}
        except (OSError, ValueError):
            return {constants.KEY_STATUS: constants.STATUS_RETRY}
        return uninstall(remove_plugins=False, locked=True, discover=False)
    finally:
        lock.close()
