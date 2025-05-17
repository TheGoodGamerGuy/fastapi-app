import json
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os

MQTT_BROKER = "host.docker.internal"
MQTT_PORT = 1883
MQTT_TOPIC = "plant1/#"
INFLUXDB_URL = "host.docker.internal:8086"
INFLUXDB_ORG = "DataForge"
INFLUXDB_BUCKET = "mqtt"
INFLUXDB_TOKEN = os.environ.get('INFLUX_TOKEN')

influx_client = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT Broker" if rc == 0 else f"Connection failed, rc: {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode().replace("'", '"'))
        sensor_name = data.get("node_id", "unknown_sensor")
        sensor_value = float(data.get("value", 0))
        
        point = Point("sensor_data").tag("sensor", sensor_name).field("value", sensor_value)
        write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=point)
        print(f"Data written: {sensor_name} = {sensor_value}")
    except Exception as e:
        print(f"Error processing message: {e}")

def connect_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        print("MQTT client connection initiated")
        return client
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return None

# Main execution
try:
    print("Connecting to MQTT Broker...")
    mqtt_client = connect_mqtt()
    if mqtt_client:
        # Start the loop only if connection was successful
        mqtt_client.loop_forever()
    else:
        print("Failed to establish MQTT connection")
except Exception as e:
    print(f"Error in main execution: {e}")