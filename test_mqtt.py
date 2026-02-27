"""
ESY Sunhome MQTT Test Script

Usage:
    python test_mqtt.py --username your@email.com --password yourpassword

This script connects to the ESY MQTT broker and listens for battery status updates.
"""

import paho.mqtt.client as mqtt
import time
import json
import argparse
import requests


def main():
    parser = argparse.ArgumentParser(description="ESY Sunhome MQTT Test")
    parser.add_argument("--username", required=True, help="ESY app username/email")
    parser.add_argument("--password", required=True, help="ESY app password")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--device-sn", help="Device serial number (optional)")
    args = parser.parse_args()

    BASE_URL = args.api_url

    # 1. Login
    print(f"Logging in to {BASE_URL}...")
    r = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": args.username, "password": args.password},
        timeout=15
    )
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text}")
        return
    
    result = r.json()
    token = result.get("token")
    device_sn = args.device_sn or result.get("device_sn")
    
    print(f"Logged in! Token: {token[:20]}...")
    print(f"Device SN: {device_sn}")

    # 2. Trigger update to request data from the inverter
    print("Triggering status update...")
    requests.get(
        f"{BASE_URL}/status",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5
    )

    # 3. Subscribe to MQTT
    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"MQTT Connected: {rc}")
        # Subscribe to APP topic with device SN
        client.subscribe(f"/APP/{device_sn}/NEWS")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            val_str = payload.get("val", "{}")
            # val is a JSON string inside JSON
            val = json.loads(val_str)
            
            print("\n" + "="*50)
            print("=== Battery Status ===")
            print(f"  Battery SOC: {val.get('batterySoc')}%")
            print(f"  Battery Power: {val.get('batteryPower')}W")
            print(f"  Battery Status: {val.get('batteryStatus')}")
            print(f"  PV Power: {val.get('pvPower')}W")
            print(f"  PV1 Power: {val.get('pv1Power')}W")
            print(f"  PV2 Power: {val.get('pv2Power')}W")
            print(f"  Grid Power: {val.get('gridPower')}W")
            print(f"  Load Power: {val.get('loadPower')}W")
            print(f"  Daily Generation: {val.get('dailyPowerGeneration')}kWh")
            print(f"  Mode (code): {val.get('code')}")
            print("="*50)
        except Exception as e:
            print(f"Error parsing message: {e}")

    print(f"\nConnecting to MQTT broker...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set("app", "tKQyP52RUZWMPQBtKnMh")
    client.on_connect = on_connect
    client.on_message = on_message
    
    # Connect to ESY MQTT broker (non-TLS port 1883)
    client.connect("abroadtcp.esysunhome.com", 1883, 60)
    client.loop_start()

    print(f"Waiting for messages on /APP/{device_sn}/NEWS ...")
    print("Press Ctrl+C to exit")
    
    try:
        while True:
            time.sleep(10)
            # Periodically trigger updates
            try:
                requests.get(
                    f"{BASE_URL}/status",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5
                )
            except:
                pass
    except KeyboardInterrupt:
        print("\nExiting...")
    
    client.loop_stop()


if __name__ == "__main__":
    main()
