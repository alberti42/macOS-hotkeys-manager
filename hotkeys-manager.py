#!/usr/bin/env python3

import subprocess
import argparse
import getpass
import json
import plistlib
import sys
import os
import tempfile
from typing import Any, Dict, List, Tuple

UNIVERSAL_ACCESS = "com.apple.universalaccess"
CUSTOM_MENU_KEY = "com.apple.custommenu.apps"
KEY_EQUIVALENTS = "NSUserKeyEquivalents"
# System Settings calls this one "All Applications".
GLOBAL_DOMAIN = "NSGlobalDomain"
TROUBLESHOOTING_URL = "https://github.com/alberti42/macOS-hotkeys-manager#-troubleshooting"

# Exit codes
EXIT_OK = 0        # everything applied
EXIT_FAILURE = 1   # hotkeys could not be written (the shortcuts did not get applied)
EXIT_PARTIAL = 2   # hotkeys written and working, but App Shortcuts registration was rejected


def warn(message: str = "") -> None:
    """Print to stderr, flushing stdout first so interleaved output stays in order."""
    sys.stdout.flush()
    print(message, file=sys.stderr, flush=True)


def read_domain(domain: str) -> Dict[str, Any]:
    """Read a whole preference domain as a dict. Returns {} if missing or unreadable.

    The export goes to a file, not to stdout: `defaults` writes XML to stdout but a binary
    plist to a file. That matters because a shortcut bound to Escape holds a raw 0x1b, and
    `defaults` emits control characters into its XML unescaped, which makes the XML
    malformed and Python refuses to parse it. A binary plist has no such restriction.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "domain.plist")
        try:
            subprocess.run(
                ["defaults", "export", domain, path],
                capture_output=True, check=True
            )
            with open(path, "rb") as f:
                return plistlib.load(f) or {}
        except (subprocess.CalledProcessError, OSError,
                plistlib.InvalidFileException, ValueError):
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
    """Report a rejected write to the universalaccess domain, pointing at the docs."""
    warn(f"⚠️  Could not update {UNIVERSAL_ACCESS} → {CUSTOM_MENU_KEY}")
    if stderr:
        warn(f"   {stderr}")
    warn(
        "\n   The apps below were not registered, so they won't appear under\n"
        "   System Settings → Keyboard → Keyboard Shortcuts → App Shortcuts.\n"
        "\n"
        "   This write is reported to be blocked on some systems — possibly a sandbox\n"
        "   restriction on this domain; on machines with SIP disabled it goes through.\n"
        "   Two workarounds tend to help:\n"
        "     • Add one shortcut per affected app by hand via App Shortcuts → +, then\n"
        "       re-run this import.\n"
        "     • Disable SIP (a security tradeoff — not generally recommended).\n"
        f"   Details: {TROUBLESHOOTING_URL}"
    )
    if missing_apps:
        warn(f"\n   Apps still missing from {CUSTOM_MENU_KEY}:")
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


def domains_with_shortcuts() -> List[str]:
    """Registered apps, plus "All Applications" when it holds shortcuts unregistered.

    System Settings adds NSGlobalDomain to custommenu.apps when you create an All
    Applications shortcut, but a shortcut set directly with `defaults write -g` never
    gets registered, so scanning custommenu.apps alone would miss it.
    """
    apps = list_custom_apps()
    if GLOBAL_DOMAIN not in apps and read_key_equivalents(GLOBAL_DOMAIN):
        apps.append(GLOBAL_DOMAIN)
    return apps


def write_key_equivalents(domain: str, key_map: Dict[str, str]) -> Tuple[bool, str]:
    return write_value(domain, KEY_EQUIVALENTS, key_map)


def delete_key_equivalents(domain: str) -> Tuple[bool, str]:
    return delete_value(domain, KEY_EQUIVALENTS)


def export_shortcuts(filename: str) -> int:
    apps = domains_with_shortcuts()
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
    """Add bundle IDs to custommenu.apps. Returns the number of failures.

    The array is stored sorted and de-duplicated so the same set of apps always produces
    the same plist, which keeps it diffable if you track it in a dotfiles repo.
    """
    existing = list_custom_apps()
    new_apps = [app for app in wanted if app not in existing]

    if not new_apps:
        print(f"ℹ️  All {len(wanted)} app(s) already registered in {CUSTOM_MENU_KEY}.")
        return 0

    ok, stderr = write_value(UNIVERSAL_ACCESS, CUSTOM_MENU_KEY, sorted(set(existing) | set(new_apps)))

    # Confirm by reading the value back, not by trusting the exit status alone, so a write
    # that is rejected or silently changes nothing is caught instead of reported as success.
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

    # Register the bundle IDs first, so a rejected write is reported up front rather
    # than after the per-app writes have already gone through. A rejected registration is
    # not fatal: the per-app writes below still apply and the shortcuts still work; only
    # their visibility in System Settings is lost.
    registration_failed = register_custom_apps(list(data.keys())) > 0

    app_failures = 0
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
            app_failures += 1
        else:
            print(f"→ Updated hotkeys for {app}")

    refresh_preferences()

    # A hotkey that could not be written is a hard failure and takes precedence: those
    # shortcuts are not in effect. Report it and stop here.
    if app_failures:
        warn(f"\n❌ Import failed: {app_failures} app(s) could not be written; see above.")
        return EXIT_FAILURE

    # Otherwise the shortcuts are applied and working. A rejected registration only means
    # the apps won't appear in System Settings — a partial success, not a failure.
    if registration_failed:
        warn(
            "\n⚠️  Import partly succeeded: the hotkeys were written and are active, but the\n"
            "   affected apps could not be registered in System Settings → Keyboard →\n"
            "   Keyboard Shortcuts → App Shortcuts (see above). They work; they just won't\n"
            "   show up there."
        )
        return EXIT_PARTIAL

    return EXIT_OK


def reset_shortcuts() -> int:
    apps = domains_with_shortcuts()
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

    app_failures = 0
    for app in apps:
        ok, stderr = delete_key_equivalents(app)
        if ok:
            print(f"🗑 Removed hotkeys for {app}")
        else:
            report_app_failure(app, stderr)
            app_failures += 1

    ok, stderr = delete_value(UNIVERSAL_ACCESS, CUSTOM_MENU_KEY)
    registration_cleanup_failed = not ok or bool(list_custom_apps())
    if registration_cleanup_failed:
        warn(f"⚠️  Could not clear {UNIVERSAL_ACCESS} → {CUSTOM_MENU_KEY}")
        if stderr:
            warn(f"   {stderr}")

    refresh_preferences()

    # A hotkey that could not be deleted is a hard failure: the shortcut is still active.
    if app_failures:
        warn(f"\n❌ Reset failed: {app_failures} app(s) could not be cleared; see above.")
        return EXIT_FAILURE

    # The hotkeys are gone; only the System Settings tracker could not be cleared, so the
    # apps may still be listed under App Shortcuts. That is a partial success, not a failure.
    if registration_cleanup_failed:
        warn(
            "\n⚠️  Reset partly succeeded: the hotkeys were removed, but the App Shortcuts\n"
            "   list in System Settings could not be cleared (see above), so those apps may\n"
            "   still appear there."
        )
        return EXIT_PARTIAL

    print("✅ Reset complete. All custom hotkeys and tracking removed.")
    return EXIT_OK


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
