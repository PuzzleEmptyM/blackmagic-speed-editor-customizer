# ─────────────────────────────────────────────────────────────────────────────
# File: dump_all_reports.py
# ─────────────────────────────────────────────────────────────────────────────

import time
from pywinusb import hid

VENDOR_ID  = 0x1EDB  # Your Speed Editor VID
PRODUCT_ID = 0xDA0E  # Your Speed Editor PID

def input_handler(data):
    """
    Called for any incoming input-report (e.g. button presses).
    data[0] = Report ID
    data[1:] = payload bytes
    """
    report_id = data[0]
    hex_bytes = " ".join(f"{b:02x}" for b in data)
    print(f"[INPUT-REPORT]  ReportID=0x{report_id:02x}  Raw={hex_bytes}")

def feature_handler(data):
    """
    Called when we explicitly poll a feature-report via rpt.get().
    data[0] = Report ID
    data[1:] = payload bytes
    """
    report_id = data[0]
    hex_bytes = " ".join(f"{b:02x}" for b in data)
    print(f"[FEATURE-REPORT] ReportID=0x{report_id:02x}  Raw={hex_bytes}")

def main():
    # 1) Locate the Speed Editor by VID/PID
    all_devices = hid.HidDeviceFilter(vendor_id=VENDOR_ID, product_id=PRODUCT_ID).get_devices()
    if not all_devices:
        print("⚠️  Speed Editor not found. Make sure it’s plugged in and DaVinci Resolve is closed.")
        return

    device = all_devices[0]
    device.open()

    # 2) Install handler for *input*-reports (buttons, etc.)
    device.set_raw_data_handler(input_handler)
    print("🟢 Listening for input-reports (buttons)…")

    # 3) Find all feature reports
    feature_reports = device.find_feature_reports()
    if not feature_reports:
        print("⚠️  No feature reports found. (Ensure Resolve is closed so the HID interface is free.)")
    else:
        print(f"🔍 Found {len(feature_reports)} feature report(s).")
        for rpt in feature_reports:
            print(f"   • Feature Report: report_id=0x{rpt.report_id:02x}")

    print("\nListening to all input + feature reports. Press Ctrl+C to exit.\n")

    try:
        # 4) Poll each feature-report every second so you catch dial/jog values
        while True:
            for rpt in feature_reports:
                data = rpt.get()  # returns a list of ints, or None if no data
                if data:
                    feature_handler(data)
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n👋 Exiting…")
    finally:
        device.close()

if __name__ == "__main__":
    main()
