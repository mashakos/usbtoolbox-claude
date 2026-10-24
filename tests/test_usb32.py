"""Regression tests for the USB 3.20 xHCI patch (run on any OS; no Windows APIs needed).

Usage:  TOOL_DIR=path/to/patched/USBToolBox/tool python tests/test_usb32.py
"""
import json
import os
import sys
from pathlib import Path
from unittest import mock

TOOL_DIR = Path(os.environ.get("TOOL_DIR", "tool")).resolve()
sys.path.insert(0, str(TOOL_DIR))
os.chdir(TOOL_DIR)

import base  # noqa: E402

base.BaseUSBMap.monu = lambda self: None  # Windows.py instantiates its class at import time and would open the TUI

import Windows  # noqa: E402
from Scripts import shared, usbdump  # noqa: E402


def port(idx, connected=False):
    return {
        "PortConnectorProps": {"ConnectionIndex": idx, "UsbPortProperties": {"PortConnectorIsTypeC": True}},
        "ConnectionInfo": {"ConnectionStatus": "DeviceConnected" if connected else "NoDeviceConnected", "Speed": 3, "ConnectionIndex": idx, "DeviceDescriptor": {"iProduct": 0}},
        "ConnectionInfoV2": {"SupportedUsbProtocols": {"Usb300": 1, "Usb200": 1, "Usb110": 1}, "Flags": {}},
        "UsbDeviceProperties": {"DeviceId": "USB\\X", "DeviceDesc": "Dev"} if connected else None,
        "DeviceInfoNode": None,
        "StringDescs": None,
        "DeviceInfoType": "Device",
    }


def hub(name, nports, with_info=True):
    h = {"HubName": name, "HubPorts": [port(i + 1) for i in range(nports)]}
    h["HubInfo"] = {"HubInformation": {"HubDescriptor": {"bNumberOfPorts": nports}}} if with_info else None
    return h


def host_controller(desc, dev, root, props=True):
    return {
        "VendorID": 0x8086,
        "DeviceID": dev,
        "SubSysID": 0x72708086,
        "BusDeviceFunctionValid": True,
        "BusNumber": 0,
        "BusDevice": 13,
        "BusFunction": 0,
        "ControllerInfo": {"PciRevision": 1},
        "UsbDeviceProperties": {"DeviceDesc": desc, "DeviceId": f"PCI\\VEN_8086&DEV_{dev:04X}\\3&0"} if props else None,
        "RootHub": root,
    }


def test_controller_serialization():
    dump = [
        host_controller("Intel(R) USB 3.10 eXtensible Host Controller - 1.20 (Microsoft)", 0xA0ED, hub("ROOTHUB_A", 5)),
        host_controller("Intel(R) USB 3.20 eXtensible Host Controller - 1.20 (Microsoft)", 0x9A13, hub("ROOTHUB_B", 4, with_info=False)),  # HubInfo is null
        host_controller("Intel(R) USB 3.20 eXtensible Host Controller - 1.20 (Microsoft)", 0x9A14, None),  # root hub unreadable
        host_controller(None, 0x1234, hub("ROOTHUB_C", 2), props=False),  # no device properties at all
        host_controller("Broken", 0x1235, {"HubName": "ROOTHUB_D", "HubPorts": [{"ConnectionInfo": None, "PortConnectorProps": None}]}),  # malformed
    ]
    with mock.patch.object(usbdump.subprocess, "run", return_value=mock.Mock(stdout=json.dumps(dump).encode())):
        out = usbdump.get_controllers()

    assert len(out) == 3, [c["name"] for c in out]
    usb320 = out[1]
    assert "3.20" in usb320["name"]
    assert usb320["port_count"] == 4 and len(usb320["ports"]) == 4
    assert usb320["identifiers"]["pci_id"][:2] == ["8086", "9a13"]
    reasons = dict(usbdump.skipped_controllers)
    assert "root hub" in reasons["Intel(R) USB 3.20 eXtensible Host Controller - 1.20 (Microsoft)"]
    assert "Broken" in reasons


def test_is_same_controller():
    B = base.BaseUSBMap
    assert B.is_same_controller({"identifiers": {"instance_id": "X"}}, {"identifiers": {"instance_id": "X"}}) is False
    c1 = {"identifiers": {"instance_id": "1", "pci_id": ["8086", "9a13"], "bdf": [0, 13, 0]}}
    c2 = {"identifiers": {"instance_id": "2", "pci_id": ["8086", "9a13"], "bdf": [0, 13, 0]}}
    c3 = {"identifiers": {"instance_id": "3", "pci_id": ["8086", "a0ed"], "bdf": [0, 20, 0]}}
    assert B.is_same_controller(c1, c2)  # same controller after a Thunderbolt hotplug changed the instance id
    assert not B.is_same_controller(c1, c3)


def test_windows_helpers():
    w = Windows.WindowsUSBMap.__new__(Windows.WindowsUSBMap)
    vals = {"DEVPKEY_PciDevice_ProgIf": 0x40, "DEVPKEY_Device_Service": "USBXHCI"}  # 0x40 = USB4 host interface, not in our enum
    w.get_property_from_wmi = lambda iid, prop: vals.get(prop.value)
    ctl = {"name": "x", "identifiers": {"instance_id": "PCI\\VEN_8086"}}
    assert w.get_controller_class(ctl) == shared.USBControllerTypes.XHCI
    assert Windows.WindowsUSBMap.escape_wql("PCI\\VEN_8086&DEV\\3&0'x") == "PCI\\\\VEN_8086&DEV\\\\3&0\\'x"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("ALL OK")
