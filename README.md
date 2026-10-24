# USBToolBox – Intel(R) USB 3.20 eXtensible Host Controller support

Patches + CI for [USBToolBox/tool](https://github.com/USBToolBox/tool) (and its helper
[USBToolBox/usbdump](https://github.com/USBToolBox/usbdump)) so that
`Intel(R) USB 3.20 eXtensible Host Controller - 1.20 (Microsoft)` is no longer lost during
port discovery. Upstream stays untouched; the workflow checks out pinned upstream commits and applies the patches.

| Patch | Applies to | What it changes |
|---|---|---|
| `patches/0001-tool-support-intel-usb-3.20-xhci.patch` | `USBToolBox/tool@0c6823a` | Python side (details below) |
| `patches/usbdump-0001-robust-host-controller-enumeration.patch` | `USBToolBox/usbdump@51adc70` | C++ enumerator (details below) |

## Why the controller was missing

`usbdump.exe` aborted or skipped controllers silently, and the Python layer dropped what was left:

* **usbdump** looped over `SetupDiEnumDeviceInfo` while indexing `SetupDiEnumDeviceInterfaces` with the same counter (the two lists
  don't have to line up – virtual controllers like VirtualHere/Nefarius break that) and did `break` on the first error, so every controller after
  a failing one disappeared. Hub/controller handles were opened with one fixed access/share mode and any refusal returned `NULL` with no trace.
* **tool** discarded any controller without a root hub, crashed/aborted on null `HubInfo`/`UsbDeviceProperties`, crashed on an unknown PCI ProgIf
  (e.g. `0x40`, USB4), and `is_same_controller()` treated two controllers sharing only an `instance_id` as identical (merging one away).

## What the patches do

**usbdump**: walk device *interfaces* and `continue` on per-controller errors; use the `SP_DEVINFO_DATA` of each interface for bus/device/function;
fall back to more permissive `CreateFile` access/share modes for host-controller and hub handles; new `--debug` / `USBDUMP_DEBUG=1`
logs every failing step (with `GetLastError`) to **stderr** – stdout stays valid JSON.

**tool**: tolerate null hub info / device properties / PCI IDs, isolate failures per controller, and show anything that still can't be read in a
*"controllers were found but could not be enumerated"* list instead of hiding it; no crash on unknown ProgIf; WQL-escape instance IDs; never merge
controllers on `instance_id` alone.

## Build

Push to `main` (or run the workflow manually). Jobs: `test` (patches apply + unit tests) → `usbdump` (MSVC, x64) → `windows`
(`Windows.exe`, `Windows.zip`, `debug_dump.*`, using the freshly built patched `usbdump.exe`) and `macos` (arm64 + x86_64 zips).
Push a `v*` tag to publish a GitHub release with everything attached.

Manual: `git apply patches/0001-*.patch` inside a `USBToolBox/tool` checkout, `git apply patches/usbdump-0001-*.patch` inside `usbdump`,
build usbdump with CMake/VS 2022, copy `usbdump.exe` to `tool/resources/`, then `pyinstaller spec/Windows.spec`.

Notes: PyInstaller is pinned to 5.x because upstream's `.spec` files use `cipher=`, removed in PyInstaller 6. macOS binaries are unsigned
(`xattr -d com.apple.quarantine macOS` after download). To track newer upstream, bump `TOOL_REF` / `USBDUMP_REF` in the workflow and refresh the patches.

## If the 3.20 controller still doesn't show

Run on the affected machine and attach `debug.txt` to an issue:

```
usbdump.exe --debug > out.json 2> debug.txt
```

Every step that fails for that controller (open, root hub name, hub IOCTLs) is logged there.
