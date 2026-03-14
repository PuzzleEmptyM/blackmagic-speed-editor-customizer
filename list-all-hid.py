import time
from pywinusb import hid

def pretty_hex(x):
    return hex(x) if isinstance(x, int) else x

def main():
    print("\n──┤ Enumerating all HID devices on this machine ├──")
    devices = hid.HidDeviceFilter().get_devices()

    if not devices:
        print("⚠️  No HID devices found on this system.\n"
              "    (Is your Speed Editor plugged in? Is any USB cable faulty?)")
        return

    # Print a header
    print(f"Total HID devices found: {len(devices)}\n")

    # Walk through every HID device and print relevant fields
    for idx, d in enumerate(devices):
        vid = d.vendor_id
        pid = d.product_id
        path = d.device_path
        serial = d.serial_number or "<no-serial>"
        name = d.product_name or "<unnamed>"

        print(f"[{idx:02d}] “{name}”")
        print(f"       • VID:PID = {pretty_hex(vid)}:{pretty_hex(pid)}")
        print(f"       • SerialNumber = {serial}")
        print(f"       • DevicePath   = {path}")
        # Also show usage_page / usage to help narrow down if it’s a keyboard-like device
        try:
            print(f"       • UsagePage = {hex(d.hid_caps.usage_page)}, "
                  f"Usage = {hex(d.hid_caps.usage)}")
        except Exception:
            pass
        print("")

    print("──┤ Done ├──\n")

    # Next, check specifically for Speed Editor’s reported VID/PID
    TARGET_VID = 0x1EDB
    TARGET_PID = 0xDA0E
    print(f"Searching specifically for VID=0x{TARGET_VID:04x}, PID=0x{TARGET_PID:04x}...\n")
    matches = [d for d in devices if (d.vendor_id == TARGET_VID and d.product_id == TARGET_PID)]
    if not matches:
        print(f"❌ No matching devices found for 0x{TARGET_VID:04x}:0x{TARGET_PID:04x}.")
        print("   → If your Speed Editor is in a different mode or firmware, it may use a different PID.")
        print("   → Try looking in the list above for a Blackmagic‐looking product name or VID=0x1EDB with another PID.")
    else:
        print(f"✅ Found {len(matches)} device(s) with VID=0x{TARGET_VID:04x}, PID=0x{TARGET_PID:04x}:")
        for m in matches:
            print(f"    • “{m.product_name}” at {m.device_path}")
        print("\nYou can now modify your dump‐script to use the correct VID/PID or DevicePath.")

if __name__ == "__main__":
    main()
