#!/usr/bin/env python3

import subprocess
import argparse
import json
import plistlib
import sys
import os
from typing import Any, Dict, List

UNIVERSAL_ACCESS = "com.apple.universalaccess"
CUSTOM_MENU_KEY = "com.apple.custommenu.apps"
KEY_EQUIVALENTS = "NSUserKeyEquivalents"


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


def write_value(domain: str, key: str, value: Any) -> None:
    """Write one key as an XML plist, so quotes, backslashes and Unicode survive intact."""
    subprocess.run(
        ["defaults", "write", domain, key, plistlib.dumps(value).decode("utf-8")]
    )


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


def write_key_equivalents(domain: str, key_map: Dict[str, str]) -> None:
    write_value(domain, KEY_EQUIVALENTS, key_map)


def delete_key_equivalents(domain: str) -> None:
    subprocess.run(["defaults", "delete", domain, KEY_EQUIVALENTS], stderr=subprocess.DEVNULL)


def export_shortcuts(filename: str) -> None:
    apps = list_custom_apps()
    exported: Dict[str, Dict[str, str]] = {}

    for app in apps:
        keymap = read_key_equivalents(app)
        if keymap:
            exported[app] = keymap

    with open(filename, "w") as f:
        json.dump(exported, f, indent=2, ensure_ascii=False)
    print(f"✅ Exported hotkeys to {filename}")


def refresh_preferences() -> None:
    try:
        subprocess.run(["killall", "cfprefsd"], check=True)
        print("🔄 Reloaded macOS preference cache (cfprefsd)")
    except subprocess.CalledProcessError:
        print("⚠️ Could not reload cfprefsd (maybe it was already stopped?)")


def import_shortcuts(filename: str, force: bool = False) -> None:
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        sys.exit(1)

    with open(filename, "r") as f:
        data: Dict[str, Dict[str, str]] = json.load(f)

    existing_apps = set(list_custom_apps())
    all_apps = set(data.keys())

    # Import shortcuts
    for app, keymap in data.items():
        existing_keymap = read_key_equivalents(app)
        updated = False

        for menu_name, new_key in keymap.items():
            if menu_name in existing_keymap:
                old_key = existing_keymap[menu_name]
                if old_key == new_key:
                    continue  # Already identical
                elif force:
                    existing_keymap[menu_name] = new_key
                    print(f"↪ Overwriting '{menu_name}' in {app}: '{old_key}' → '{new_key}'")
                    updated = True
                else:
                    print(f"⚠️  Skipping '{menu_name}' in {app}: already assigned to '{old_key}', not overwritten.")
            else:
                existing_keymap[menu_name] = new_key
                updated = True

        if updated:
            write_key_equivalents(app, existing_keymap)
            print(f"→ Updated hotkeys for {app}")

    # Update com.apple.custommenu.apps
    new_apps = all_apps - existing_apps
    updated_app_list = list(existing_apps.union(new_apps))

    write_value(UNIVERSAL_ACCESS, CUSTOM_MENU_KEY, updated_app_list)
    print(f"✅ Updated custommenu.apps with {len(new_apps)} new entries.")
    refresh_preferences()


def reset_shortcuts() -> None:
    apps = list_custom_apps()
    if not apps:
        print("ℹ️  No custom hotkeys found to reset.")
        return

    print("⚠️  This will remove all custom hotkeys for the following apps:")
    for app in apps:
        print(f"   - {app}")
    confirm = input("❓ Are you sure you want to reset all hotkeys? [y/N]: ").strip().lower()
    if confirm != 'y':
        print("❌ Reset cancelled.")
        return

    for app in apps:
        delete_key_equivalents(app)
        print(f"🗑 Removed hotkeys for {app}")

    subprocess.run([
        "defaults", "delete", UNIVERSAL_ACCESS, CUSTOM_MENU_KEY
    ], stderr=subprocess.DEVNULL)
    print("✅ Reset complete. All custom hotkeys and tracking removed.")
    refresh_preferences()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export, import, or reset macOS custom menu hotkeys")
    parser.add_argument("--export", metavar="FILE", help="Export hotkeys to JSON")
    parser.add_argument("--import", dest="import_file", metavar="FILE", help="Import hotkeys from JSON")
    parser.add_argument("--force", action="store_true", help="Force overwrite of conflicting hotkeys during import")
    parser.add_argument("--reset", action="store_true", help="Reset (remove) all custom hotkeys")
    args = parser.parse_args()

    if args.export:
        export_shortcuts(args.export)
    elif args.import_file:
        import_shortcuts(args.import_file, force=args.force)
    elif args.reset:
        reset_shortcuts()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
