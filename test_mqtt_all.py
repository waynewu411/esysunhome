"""
ESY Sunhome MQTT Debug Script - Listen to ALL messages

Usage:
    python test_mqtt_all.py --mqtt-user app --mqtt-pass YOUR_MQTT_PASSWORD

This script subscribes to ALL topics to see what's available.
"""

import paho.mqtt.client as mqtt
import time
import json
import argparse


def main():
    parser = argparse.ArgumentParser(description="ESY Sunhome MQTT Debug")
    parser.add_argument("--mqtt-user", default="app", help="MQTT username")
    parser.add_argument("--mqtt-pass", required=True, help="MQTT password")
    args = parser.parse_args()

    # Subscribe to ALL topics
    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"Connected: {rc}")
        client.subscribe("#")  # All topics

    def on_message(client, userdata, msg):
        topic = msg.topic
        # Only show APP topics
        if "/APP/" in topic:
            try:
                payload = json.loads(msg.payload.decode())
                val_str = payload.get("val", "")
                val = json.loads(val_str) if val_str else {}
                device_id = val.get("deviceId", "unknown")
                print(f"\n=== Topic: {topic} ===")
                print(f"  Device ID: {device_id}")
                print(f"  Battery SOC: {val.get('batterySoc')}")
                print(f"  PV Power: {val.get('pvPower')}")
            except:
                print(f"\n=== Topic: {topic} ===")
                print(f"  Raw: {msg.payload[:200]}")

    print("Connecting to MQTT broker...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(args.mqtt_user, args.mqtt_pass)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("abroadtcp.esysunhome.com", 1883, 60)
    client.loop_start()

    print("Listening to ALL /APP/* topics for 30 seconds...")
    print("Look for YOUR device (deviceId: 1960131414140485641)")
    time.sleep(30)
    client.loop_stop()


if __name__ == "__main__":
    main()
