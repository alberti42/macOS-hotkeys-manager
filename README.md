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

## 🚀 Usage

Make sure your system has Python 3 installed (pre-installed on macOS), then run:

```bash
chmod +x hotkeys_manager.py
./hotkeys_manager.py [option]
```

### Export custom hotkeys

```bash
./hotkeys_manager.py --export my_hotkeys.json
```

This will create a JSON file with all current app-specific and global hotkeys.

---

### Import hotkeys from file

```bash
./hotkeys_manager.py --import my_hotkeys.json
```

By default, the script **does not overwrite** any existing hotkey entries that differ. It skips them with a warning.

To forcefully overwrite all conflicting entries:

```bash
./hotkeys_manager.py --import my_hotkeys.json --force
```

---

### Reset all hotkeys

```bash
./hotkeys_manager.py --reset
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

This tool:
- Reads from those domains using `defaults`
- Outputs valid JSON
- Imports them back while preserving existing entries (unless `--force` is used)
- Reloads the system preference daemon (`cfprefsd`) to apply changes immediately

---

## 📦 Requirements

- macOS 10.10 or newer
- Python 3.x
- No third-party packages needed

---

## 📎 Example Workflow

```bash
# On your main machine
./hotkeys_manager.py --export my_hotkeys.json

# Copy file to a second machine (e.g., via AirDrop, scp, email, usb stick, Git, etc.)
scp my_hotkeys.json user@newmac.local:~

# On the second machine
./hotkeys_manager.py --import my_hotkeys.json
```

---

## 🛡️ Safety Notes

- No system-level files are touched — only user preferences.
- `killall cfprefsd` is called automatically to refresh changes without requiring logout.

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
