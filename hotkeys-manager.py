#!/usr/bin/env python3

import subprocess
import argparse
import getpass
import json
import plistlib
import sys
import os
from typing import Any, Dict, List, Tuple

UNIVERSAL_ACCESS = "com.apple.universalaccess"
CUSTOM_MENU_KEY = "com.apple.custommenu.apps"
KEY_EQUIVALENTS = "NSUserKeyEquivalents"


def warn(message: str = "") -> None:
    """Print to stderr, flushing stdout first so interleaved output stays in order."""
    sys.stdout.flush()
    print(message, file=sys.stderr, flush=True)


def read_domain(domain: str) -> Dict[str, Any]:
    """Read a whole preference domain as a dict. Returns {} if missing or unreadable."""
    try:
        output = subprocess.run(
            ["defaults", "export", domain, "-"],
            capture_output=True, check=True
        ).stdout
        return plistlib.loads(output) or {}
    except (subprocess.CalledProcessError, plistlib.InvalidFileException, ValueError):
        return {}


def write_value(domain: str, key: str, value: Any) -> Tuple[bool, str]:
    """Write one key as an XML plist, so quotes, backslashes and Unicode survive intact."""
    result = subprocess.run(
        ["defaults", "write", domain, key, plistlib.dumps(value).decode("utf-8")],
        capture_output=True, text=True
    )
    stderr = result.stderr.strip()
    ok = result.returncode == 0 and "Could not write domain" not in stderr
    return ok, stderr


def delete_value(domain: str, key: str) -> Tuple[bool, str]:
    result = subprocess.run(
        ["defaults", "delete", domain, key],
        capture_output=True, text=True
    )
    stderr = result.stderr.strip()
    # A missing key is not a failure — there was nothing to remove.
    if "does not exist" in stderr or "not found" in stderr.lower():
        return True, ""
    ok = result.returncode == 0 and "Could not write domain" not in stderr
    return ok, stderr


def report_universalaccess_failure(stderr: str, missing_apps: List[str]) -> None:
    """Explain a rejected write to the TCC-protected universalaccess domain."""
    warn(f"❌ Failed to update {UNIVERSAL_ACCESS} → {CUSTOM_MENU_KEY}")
    if stderr:
        warn(f"   {stderr}")
    warn(
        "\n   macOS protects this domain with TCC. `defaults write` succeeds only when the\n"
        "   terminal running this script has been granted Full Disk Access.\n"
        "\n"
        "   Preferred fix:\n"
        "     System Settings → Privacy & Security → Full Disk Access → enable your\n"
        "     terminal app, quit and reopen it, then run this import again.\n"
        "\n"
        "   Fallback, if you cannot grant Full Disk Access:\n"
        "     System Settings → Keyboard → Keyboard Shortcuts… → App Shortcuts → +\n"
        "     Add one shortcut for each app listed below; macOS registers the bundle ID\n"
        "     itself. Then run this import AGAIN — the App Shortcuts pane rewrites\n"
        f"     {KEY_EQUIVALENTS} wholesale and can drop entries written here."
    )
    if missing_apps:
        warn(f"\n   Still missing from {CUSTOM_MENU_KEY}:")
        for app in missing_apps:
            warn(f"     - {app}")
    warn()


def report_app_failure(app: str, stderr: str) -> None:
    warn(f"❌ Failed to write {KEY_EQUIVALENTS} for {app}")
    if stderr:
        warn(f"   {stderr}")


def list_custom_apps() -> List[str]:
    apps = read_domain(UNIVERSAL_ACCESS).get(CUSTOM_MENU_KEY, [])
    if not isinstance(apps, list):
        return []
    return [app for app in apps if isinstance(app, str)]


def read_key_equivalents(domain: str) -> Dict[str, str]:
    keymap = read_domain(domain).get(KEY_EQUIVALENTS)
    if not isinstance(keymap, dict):
        return {}
    return {k: v for k, v in keymap.items() if isinstance(k, str) and isinstance(v, str)}


def write_key_equivalents(domain: str, key_map: Dict[str, str]) -> Tuple[bool, str]:
    return write_value(domain, KEY_EQUIVALENTS, key_map)


def delete_key_equivalents(domain: str) -> Tuple[bool, str]:
    return delete_value(domain, KEY_EQUIVALENTS)


def export_shortcuts(filename: str) -> int:
    apps = list_custom_apps()
    exported: Dict[str, Dict[str, str]] = {}

    for app in apps:
        keymap = read_key_equivalents(app)
        if keymap:
            exported[app] = keymap

    with open(filename, "w") as f:
        json.dump(exported, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print(f"✅ Exported hotkeys for {len(exported)} app(s) to {filename}")
    return 0


def refresh_preferences() -> None:
    # Scoped to this user: the root-owned cfprefsd cannot be signalled from here and
    # would make an unscoped killall report a spurious failure.
    result = subprocess.run(
        ["killall", "-u", getpass.getuser(), "cfprefsd"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("🔄 Reloaded macOS preference cache (cfprefsd)")
    else:
        print("⚠️  Could not reload cfprefsd (maybe it was already stopped?)")


def register_custom_apps(wanted: List[str]) -> int:
    """Add bundle IDs to custommenu.apps. Returns the number of failures."""
    existing = list_custom_apps()
    new_apps = [app for app in wanted if app not in existing]

    if not new_apps:
        print(f"ℹ️  All {len(wanted)} app(s) already registered in {CUSTOM_MENU_KEY}.")
        return 0

    ok, stderr = write_value(UNIVERSAL_ACCESS, CUSTOM_MENU_KEY, existing + sorted(new_apps))

    # Read back rather than trusting the exit code alone: this domain has a history of
    # rejecting writes without a useful status, which is what made the failure silent.
    still_missing = [app for app in new_apps if app not in list_custom_apps()]

    if not ok or still_missing:
        report_universalaccess_failure(stderr, still_missing or new_apps)
        return 1

    print(f"✅ Registered {len(new_apps)} new app(s) in {CUSTOM_MENU_KEY}.")
    return 0


def import_shortcuts(filename: str, force: bool = False) -> int:
    if not os.path.exists(filename):
        warn(f"❌ File not found: {filename}")
        return 1

    with open(filename, "r") as f:
        data: Dict[str, Dict[str, str]] = json.load(f)

    if not data:
        print(f"ℹ️  Nothing to import: {filename} is empty.")
        return 0

    # Register the bundle IDs first, so a TCC rejection is reported up front rather
    # than after the per-app writes have already gone through.
    failures = register_custom_apps(list(data.keys()))

    for app, keymap in data.items():
        merged = read_key_equivalents(app)
        updated = False

        for menu_name, new_key in keymap.items():
            if menu_name in merged:
                old_key = merged[menu_name]
                if old_key == new_key:
                    continue  # Already identical
                elif force:
                    merged[menu_name] = new_key
                    print(f"↪ Overwriting '{menu_name}' in {app}: '{old_key}' → '{new_key}'")
                    updated = True
                else:
                    print(f"⚠️  Skipping '{menu_name}' in {app}: already assigned to '{old_key}', not overwritten.")
            else:
                merged[menu_name] = new_key
                updated = True

        if not updated:
            continue

        ok, stderr = write_key_equivalents(app, merged)
        written = read_key_equivalents(app)
        unwritten = [name for name, key in merged.items() if written.get(name) != key]

        if not ok or unwritten:
            report_app_failure(app, stderr)
            failures += 1
        else:
            print(f"→ Updated hotkeys for {app}")

    refresh_preferences()

    if failures:
        warn(f"\n⚠️  Import finished with {failures} failure(s); see the messages above.")
    return 1 if failures else 0


def reset_shortcuts() -> int:
    apps = list_custom_apps()
    if not apps:
        print("ℹ️  No custom hotkeys found to reset.")
        return 0

    print("⚠️  This will remove all custom hotkeys for the following apps:")
    for app in apps:
        print(f"   - {app}")
    confirm = input("❓ Are you sure you want to reset all hotkeys? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("❌ Reset cancelled.")
        return 0

    failures = 0
    for app in apps:
        ok, stderr = delete_key_equivalents(app)
        if ok:
            print(f"🗑 Removed hotkeys for {app}")
        else:
            report_app_failure(app, stderr)
            failures += 1

    ok, stderr = delete_value(UNIVERSAL_ACCESS, CUSTOM_MENU_KEY)
    if not ok or list_custom_apps():
        report_universalaccess_failure(stderr, list_custom_apps())
        failures += 1

    if failures:
        warn(f"\n⚠️  Reset finished with {failures} failure(s); see the messages above.")
    else:
        print("✅ Reset complete. All custom hotkeys and tracking removed.")
    refresh_preferences()
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Export, import, or reset macOS custom menu hotkeys")
    parser.add_argument("--export", metavar="FILE", help="Export hotkeys to JSON")
    parser.add_argument("--import", dest="import_file", metavar="FILE", help="Import hotkeys from JSON")
    parser.add_argument("--force", action="store_true", help="Force overwrite of conflicting hotkeys during import")
    parser.add_argument("--reset", action="store_true", help="Reset (remove) all custom hotkeys")
    args = parser.parse_args()

    if args.export:
        sys.exit(export_shortcuts(args.export))
    elif args.import_file:
        sys.exit(import_shortcuts(args.import_file, force=args.force))
    elif args.reset:
        sys.exit(reset_shortcuts())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
