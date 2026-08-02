# macOS Hotkey Manager

A Python script to **export**, **import**, and **reset** macOS application hotkeys using the `defaults` system.

## 🎯 What is this tool for?

To easily transfer your custom keyboard shortcuts across macOS machines or back them up for safety.

## ✨ Features

- ✅ Export all user-defined hotkeys (menu item shortcuts) to a JSON file
- ✅ Import them on another machine or after a reinstall
- ✅ Intelligent conflict detection (with `--force` overwrite option)
- ✅ Full reset of all configured hotkeys (with user confirmation)
- ✅ Automatically refreshes `cfprefsd` to apply changes immediately
- ✅ Clean, type-annotated Python code

---

<a id="full-disk-access"></a>

## ⚠️ Before you start: Full Disk Access

macOS protects `com.apple.universalaccess` with TCC. Writing to it — which is how apps
get registered in **System Settings → Keyboard → Keyboard Shortcuts… → App Shortcuts** —
only succeeds if the **terminal running this script** has Full Disk Access:

> System Settings → Privacy & Security → Full Disk Access → enable your terminal app,
> then quit and reopen it.

Without it, `--import` will report the failure and exit non-zero rather than pretend it
worked. See [Troubleshooting](#troubleshooting) for the fallback.

---

## 🚀 Usage

Make sure your system has Python 3 installed (pre-installed on macOS), then run:

```bash
chmod +x hotkeys-manager.py
./hotkeys-manager.py [option]
```

### Export custom hotkeys

```bash
./hotkeys-manager.py --export my_hotkeys.json
```

This will create a JSON file with all current app-specific and global hotkeys.

---

### Import hotkeys from file

```bash
./hotkeys-manager.py --import my_hotkeys.json
```

By default, the script **does not overwrite** any existing hotkey entries that differ. It skips them with a warning.

To forcefully overwrite all conflicting entries:

```bash
./hotkeys-manager.py --import my_hotkeys.json --force
```

---

### Reset all hotkeys

```bash
./hotkeys-manager.py --reset
```

This deletes:
- All `NSUserKeyEquivalents` entries from every app listed
- The global `com.apple.custommenu.apps` tracker

✅ You will be asked for confirmation before the reset is applied.

---

## 💡 How It Works

macOS stores custom menu shortcuts in `NSUserKeyEquivalents` dictionaries in `defaults` for each app. These are tracked centrally via:

```
com.apple.universalaccess → com.apple.custommenu.apps
```

The **All Applications** entry in that pane is not a real app — it is the `NSGlobalDomain`
pseudo-domain, and it is exported and imported like any other. It is picked up even when it
is missing from `com.apple.custommenu.apps`, which happens when a global shortcut was set
directly with `defaults write -g NSUserKeyEquivalents …` rather than through System Settings.

This tool:
- Reads from those domains via `defaults export`, parsed as a real property list
- Outputs valid JSON
- Imports them back while preserving existing entries (unless `--force` is used)
- Writes each value as an XML property list, so menu titles containing quotes,
  backslashes, or non-ASCII characters (`Vorwärts`, `Präsentation vorführen`) survive
  the round trip intact
- Verifies every write by reading it back, and exits non-zero if anything failed
- Reloads the system preference daemon (`cfprefsd`) to apply changes immediately

---

<a id="troubleshooting"></a>

## 🧯 Troubleshooting

### `Could not write domain com.apple.universalaccess; exiting`

Your terminal lacks Full Disk Access — see [above](#full-disk-access).
Grant it, reopen the terminal, and re-run the import.

If you cannot grant Full Disk Access, register the apps by hand instead:

1. Open **System Settings → Keyboard → Keyboard Shortcuts… → App Shortcuts → +**
2. Add **one** shortcut for each app the import listed as missing. macOS registers the
   bundle ID in `com.apple.custommenu.apps` for you.
3. Run the import **again**. This step matters: the App Shortcuts pane rewrites
   `NSUserKeyEquivalents` wholesale and can drop entries the script already wrote.

### Shortcuts imported but don't appear in System Settings

The per-app `NSUserKeyEquivalents` writes are not TCC-protected and succeed on their own,
but an app only shows up in the App Shortcuts list once its bundle ID is in
`com.apple.custommenu.apps`. That's the write above that needs Full Disk Access.

---

## 📦 Requirements

- macOS 10.10 or newer
- Python 3.x
- No third-party packages needed
- Full Disk Access for your terminal, to use `--import` and `--reset` fully

---

## 📎 Example Workflow

```bash
# On your main machine
./hotkeys-manager.py --export my_hotkeys.json

# Copy file to a second machine (e.g., via AirDrop, scp, email, usb stick, Git, etc.)
scp my_hotkeys.json user@newmac.local:~

# On the second machine
./hotkeys-manager.py --import my_hotkeys.json
```

---

## 🛡️ Safety Notes

- No system-level files are touched — only user preferences.
- `killall -u "$USER" cfprefsd` is called automatically to refresh changes without
  requiring logout. It is scoped to your own user, so the root-owned daemon is untouched.
- Writes only ever replace the `NSUserKeyEquivalents` key of an app's domain; any other
  preferences that app stores are left alone.

---

## 🛠️ Future Ideas

- 🔄 Dry-run mode to preview changes before importing
- 🌐 iCloud or dotfiles integration
- 🖼 GUI interface for visual editing
- 🧪 Unit tests for parsing and applying changes

---

## 📃 License

MIT License. Feel free to use, modify, and share.

---

## 🤝 Contributions

Issues and pull requests are welcome! If you improve the logic, add features, or build out tooling, feel free to contribute.

---

Enjoy your portable, controlled hotkey environment! 🍎⌨️
