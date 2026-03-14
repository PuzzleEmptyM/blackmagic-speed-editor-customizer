import time
from pywinusb import hid

def read_handler(data):
    print("Data received:", data)

all_devices = hid.HidDeviceFilter(vendor_id=0x1EDB, product_id=0xDA0E).get_devices()
if all_devices:
    device = all_devices[0]
    device.open()
    device.set_raw_data_handler(read_handler)
    print("Listening to Virtualizer...")
    try:
        while True:
            time.sleep(1)  # Keep running
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        device.close()
else:
    print("Device not found.")
