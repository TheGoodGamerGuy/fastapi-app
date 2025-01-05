from opcua import Client
from paho.mqtt import client as mqtt_client
import time
import json
import csv
import os

OPC_SERVER_URL = "opc.tcp://100.94.111.58:4841"
MQTT_BROKER = "host.docker.internal"
MQTT_PORT = 1883
MQTT_TOPIC = "plant1"
SELECTED_CSV = "app/data/selected.csv"
DEFAULT_READ_INTERVAL = 5

def read_selected_nodes():
    with open(SELECTED_CSV, mode='r') as file:
        return [row['NodeId'] for row in csv.DictReader(file)]

def connect_mqtt():
    client = mqtt_client.Client()
    client.connect(MQTT_BROKER, MQTT_PORT)
    print("Connected to MQTT Broker")
    return client

def read_opcua_data(opcua_client, mqtt_client):
    opcua_client.connect()
    print("Connected to OPC UA server")

    while True:
        for NodeId in read_selected_nodes():
            try:
                value = opcua_client.get_node(NodeId).get_value()
                NodeId_short = NodeId.replace("ns=2;s=DB15.", "")
                mqtt_payload = json.dumps({"NodeId": NodeId_short, "value": value})
                mqtt_client.publish(MQTT_TOPIC, mqtt_payload)
                print(f"Published: {NodeId_short} = {value}")
            except Exception as e:
                print(f"Error reading {NodeId}: {e}")
        read_interval = int(os.environ.get('READ_INTERVAL', DEFAULT_READ_INTERVAL))
        time.sleep(read_interval)

def main():
    mqtt_client = connect_mqtt()
    opcua_client = Client(OPC_SERVER_URL)
    try:
        read_opcua_data(opcua_client, mqtt_client)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        opcua_client.disconnect()
        mqtt_client.disconnect()
        print("Disconnected from servers")

if __name__ == "__main__":
    main()