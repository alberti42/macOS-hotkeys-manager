#!/usr/bin/env python3

import subprocess
import argparse
import json
import sys
import os
from typing import Dict, List, Optional


def run_defaults_command(args: List[str]) -> Optional[str]:
    try:
        output = subprocess.check_output(["defaults"] + args, stderr=subprocess.DEVNULL)
        return output.decode("utf-8")
    except subprocess.CalledProcessError:
        return None


def list_custom_apps() -> List[str]:
    output = run_defaults_command(["read", "com.apple.universalaccess", "com.apple.custommenu.apps"])
    if not output:
        return []
    try:
        cleaned = (
            output.replace("(", "[").replace(")", "]")
            .replace(";", ",").replace("=", ":")
            .replace("NSGlobalDomain", '"NSGlobalDomain"')
        )
        return json.loads(cleaned)
    except Exception:
        return []


def read_key_equivalents(domain: str) -> Optional[Dict[str, str]]:
    output = run_defaults_command(["read", domain, "NSUserKeyEquivalents"])
    if not output:
        return None
    try:
        json_output = subprocess.check_output(
            ["plutil", "-convert", "json", "-o", "-", "--", "-"],
            input=output.encode("utf-8")
        )
        return json.loads(json_output)
    except Exception:
        return None


def write_key_equivalents(domain: str, key_map: Dict[str, str]) -> None:
    plist = "{" + "".join([f'"{k}" = "{v}"; ' for k, v in key_map.items()]) + "}"
    subprocess.run(["defaults", "write", domain, "NSUserKeyEquivalents", plist])


def delete_key_equivalents(domain: str) -> None:
    subprocess.run(["defaults", "delete", domain, "NSUserKeyEquivalents"], stderr=subprocess.DEVNULL)


def export_shortcuts(filename: str) -> None:
    apps = list_custom_apps()
    exported: Dict[str, Dict[str, str]] = {}

    for app in apps:
        keymap = read_key_equivalents(app)
        if keymap:
            exported[app] = keymap

    with open(filename, "w") as f:
        json.dump(exported, f, indent=2)
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
        existing_keymap = read_key_equivalents(app) or {}
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

    apps_list_str = "(" + ", ".join(f'"{app}"' for app in updated_app_list) + ")"
    subprocess.run([
        "defaults", "write", "com.apple.universalaccess",
        "com.apple.custommenu.apps", apps_list_str
    ])
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
        "defaults", "delete", "com.apple.universalaccess", "com.apple.custommenu.apps"
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
