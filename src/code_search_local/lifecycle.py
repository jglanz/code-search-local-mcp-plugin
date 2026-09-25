"""Installation records and systemd cleanup after native marketplace removal."""

import json
import subprocess
from pathlib import Path

from . import harnesses
from .config import config_path
from .storage import ServiceLock, atomic_json, atomic_text


def state_path():
    return config_path().with_name("installation.json")


def load_state():
    return json.loads(state_path().read_text()) if state_path().exists() else {}


def merge_targets(*groups):
    return list(
        {(item["name"], item["primary"]): item for group in groups for item in group}.values()
    )


def marketplace_entries(selected):
    entries = []
    for target in selected:
        if target["name"] in ("claude", "codex"):
            entries.extend(
                {"target": target, "plugin": identifier} for identifier in harnesses.plugins(target)
            )
    if not entries:
        raise ValueError(
            "--marketplace requires an installed plugin in a selected Claude/Codex harness"
        )
    return entries


def guard_paths(unit):
    stem = unit.stem + "-marketplace"
    return [unit.with_name(stem + suffix) for suffix in (".path", ".timer", ".service")]


def remove_guard(unit):
    from .install import run

    paths = guard_paths(unit)
    for path in paths[:2]:
        if path.exists():
            run(["systemctl", "--user", "disable", "--now", path.name])
    for path in paths:
        path.unlink(missing_ok=True)


def record_installation(result, selected, entries, python):
    previous = load_state()
    state = {
        **result,
        "python": str(python),
        "targets": merge_targets(previous.get("targets", []), selected),
        "marketplace": [],
    }
    if entries:
        retained = []
        for entry in previous.get("marketplace", []):
            try:
                if entry["plugin"] not in harnesses.plugins(entry["target"]):
                    continue
            except (OSError, ValueError):
                # Preserve an unreadable profile for the watcher's later retry.
                pass
            retained.append(entry)
        combined = [*retained, *entries]
        state["marketplace"] = list(
            {
                (e["target"]["name"], e["target"]["primary"], e["plugin"]): e for e in combined
            }.values()
        )
    atomic_json(state_path(), state)
    install_guard(state)


def install_guard(state):
    from .install import run, systemd_quote

    unit = Path(state["service"])
    remove_guard(unit)
    if not state["marketplace"]:
        run(["systemctl", "--user", "daemon-reload"])
        return
    path_unit, timer_unit, service_unit = guard_paths(unit)
    watches = set()
    for entry in state["marketplace"]:
        target = entry["target"]
        watches.add(
            str(Path(target["root"]) / "plugins/installed_plugins.json")
            if target["name"] == "claude"
            else target["primary"]
        )
    if any("\n" in path or "\r" in path for path in watches):
        raise ValueError("Harness config paths cannot contain line breaks")
    atomic_text(
        path_unit,
        "[Unit]\nDescription=Code Search Local marketplace removal detection\n\n"
        "[Path]\n"
        + "".join("PathChanged=" + p.replace("%", "%%") + "\n" for p in sorted(watches))
        + f"Unit={service_unit.name}\n\n[Install]\nWantedBy=default.target\n",
    )
    atomic_text(
        timer_unit,
        "[Unit]\nDescription=Code Search Local marketplace cleanup retry\n\n"
        f"[Timer]\nOnActiveSec=30\nOnUnitInactiveSec=30\nAccuracySec=1\nUnit={service_unit.name}\n\n"
        "[Install]\nWantedBy=timers.target\n",
    )
    command = " ".join(
        systemd_quote(x) for x in (state["python"], "-m", "code_search_local", "marketplace-check")
    )
    environment = systemd_quote(
        "XDG_CONFIG_HOME=" + str(config_path().parent.parent), expand_dollars=False
    )
    atomic_text(
        service_unit,
        "[Unit]\nDescription=Code Search Local marketplace cleanup\n\n"
        f"[Service]\nType=oneshot\nExecStart={command}\nEnvironment={environment}\n"
        "Environment=PYTHONNOUSERSITE=1\nUMask=0077\n",
    )
    run(["systemctl", "--user", "daemon-reload"])
    run(["systemctl", "--user", "enable", "--now", path_unit.name, timer_unit.name])


def uninstall(*, remove_plugins=True, locked=False, discover=True):
    from .install import run, unit_path

    lock = None if locked else ServiceLock(config_path().parent, "install.lock")
    try:
        state = load_state()
        unit = Path(state.get("service", unit_path()))
        if unit.exists():
            run(["systemctl", "--user", "disable", "--now", unit.name])
            unit.unlink()
        run(["systemctl", "--user", "daemon-reload"])
        removed, errors = [], []
        for target in merge_targets(
            state.get("targets", []), harnesses.targets() if discover else []
        ):
            try:
                removed.extend(harnesses.unregister(target, remove_plugin=remove_plugins))
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                errors.append(f"{target['name']}: {error}")
        if errors:
            raise RuntimeError("Service removed; harness cleanup needs retry: " + "; ".join(errors))
        # Keep the timer available until all cleanup succeeds, so transient config errors retry.
        remove_guard(unit)
        run(["systemctl", "--user", "daemon-reload"])
        state_path().unlink(missing_ok=True)
        return {"service_removed": str(unit), "unregistered": removed, "data_preserved": True}
    finally:
        if lock is not None:
            lock.close()


def marketplace_check():
    import time

    try:
        lock = ServiceLock(config_path().parent, "install.lock")
    except RuntimeError:
        return {"status": "busy"}
    try:
        state = load_state()
        entries = state.get("marketplace", [])
        try:
            missing = [
                entry
                for entry in entries
                if entry["plugin"] not in harnesses.plugins(entry["target"])
            ]
        except (OSError, ValueError):
            return {"status": "retry"}
        if not missing:
            return {"status": "installed"}
        # Registry writes during upgrades can briefly remove an entry. Require two observations.
        time.sleep(2)
        try:
            if not any(
                entry["plugin"] not in harnesses.plugins(entry["target"]) for entry in missing
            ):
                return {"status": "installed"}
        except (OSError, ValueError):
            return {"status": "retry"}
        return uninstall(remove_plugins=False, locked=True, discover=False)
    finally:
        lock.close()
