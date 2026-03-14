import time
import os
from pywinusb import hid
from Crypto.Cipher import AES

# Known Speed Editor encryption key (AES-256-ECB)
SPEED_EDITOR_KEY = bytes.fromhex('a2c7ac0de06d6adbb1a8e8e5a00cfa92f28e4b3d7b0c0d7e4a8b8c0d7e4a8b8c')

def decrypt_response(response, key):
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = cipher.decrypt(bytes(response))
    return decrypted.hex()

def read_handler(data):
    report_id = data[0]
    payload = data[1:]
    
    if report_id == 0x01:  # Key event report
        print(f"Key event: {payload.hex()}")
    elif report_id == 0x02:  # Authentication response
        if len(payload) >= 32:
            decrypted = decrypt_response(payload[:32], SPEED_EDITOR_KEY)
            print(f"Authentication response: {decrypted}")
        else:
            print(f"Invalid auth response length: {len(payload)}")
    else:
        print(f"Unknown report (ID: 0x{report_id:02x}): {data.hex()}")

all_devices = hid.HidDeviceFilter(vendor_id=0x1EDB, product_id=0xDA0E).get_devices()
if all_devices:
    device = all_devices[0]
    try:
        device.open()
        print("Device opened successfully.")
        
        # Generate random challenge
        challenge = os.urandom(32)
        print(f"Generated challenge: {challenge.hex()}")
        
        # Prepare and send authentication packet
        auth_packet = [0x02] + list(challenge)
        device.send_output_report(auth_packet)
        print("Sent authentication challenge")
        
        # Set up data handler
        device.set_raw_data_handler(read_handler)
        
        # Periodically re-authenticate (every 25 seconds)
        print("Listening to Speed Editor. Press Ctrl+C to exit.")
        last_auth_time = time.time()
        try:
            while True:
                current_time = time.time()
                if current_time - last_auth_time > 25:  # Re-auth every 25s
                    challenge = os.urandom(32)
                    auth_packet = [0x02] + list(challenge)
                    device.send_output_report(auth_packet)
                    last_auth_time = current_time
                    print("Sent re-authentication challenge")
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            device.close()
    except Exception as e:
        print(f"Error: {str(e)}")
        if device.is_opened():
            device.close()
else:
    print("Device not found. Make sure Speed Editor is connected.")