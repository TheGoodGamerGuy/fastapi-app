# OPC UA to MQTT to InfluxDB Converter

A FastAPI application that facilitates data transfer from OPC UA servers to MQTT brokers and then to InfluxDB.

## API Endpoints

### Main Pages

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/` | Home page with converter status and controls |
| GET | `/node_selection` | Page for selecting nodes to monitor |
| GET | `/logs` | View application logs |
| GET | `/progress` | View node CSV export progress |

### Node Management

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/import_nodes_csv` | Import nodes.csv file (`file` as form data) |
| POST | `/import_selected_csv` | Import selected.csv file (`file` as form data) |
| GET | `/export_nodes_csv` | Download nodes.csv file |
| GET | `/export_selected_csv` | Download selected.csv file |
| GET | `/debug_selected_csv` | Debug endpoint to show contents of selected.csv |
| POST | `/update` | Update selected nodes (`{"NodeIds": ["ns=2;s=NodeId1", "ns=2;s=NodeId2"]}`) |

### Converter Controls

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/toggle_opcua_to_mqtt` | Toggle OPC UA to MQTT converter |
| POST | `/toggle_mqtt_to_influx` | Toggle MQTT to InfluxDB converter |
| POST | `/toggle_both_converters` | Toggle both converters with `{"turn_on": true/false}` |
| POST | `/update_read_interval` | Update polling interval with `{"interval": 5}` (seconds) |

### System Operations

| Method | URL | Description |
|--------|-----|-------------|
| POST | `/clear_logs` | Clear all log files |
| GET | `/test_mqtt` | Test MQTT broker connection |
| GET | `/get_latest_logs` | Get latest logs as JSON |
| GET | `/converter_status` | Get status of both converters |

## Data Flow

1. OPC UA server → OPC UA to MQTT converter
2. MQTT broker → MQTT to InfluxDB converter
3. InfluxDB storage

## Configuration

The system uses Docker for deployment. Key configuration:
- OPC UA server address: `opc.tcp://100.94.111.58:4841`
- MQTT broker: `host.docker.internal:1883`
- InfluxDB: `host.docker.internal:8086`

## Detailed API Usage

### Main Pages

#### GET `/`
Returns the home page with converter status and control options. The page displays:
- Current status of both converters (running/stopped)
- OPC UA read interval setting
- Controls to start/stop converters
- CSV file import/export options

#### GET `/node_selection`
Provides a page where you can select which OPC UA nodes to monitor:
- Displays a table of all available nodes
- Checkboxes to select which nodes to monitor
- "Update Selection" button to save your choices

#### GET `/logs`
Shows application logs in real-time:
- Displays logs from the main application and both converters
- Dropdown to filter logs by component
- Button to clear all logs
- Auto-refreshes to show latest entries

#### GET `/progress`
Shows the progress of node browsing/export operation:
- Displays current operation status messages
- Auto-refreshes and redirects to home when complete

### Node Management

#### POST `/import_nodes_csv`
Import a CSV file containing node definitions:

```
# Example using curl
curl -X POST -F "file=@/path/to/nodes.csv" http://localhost:8080/import_nodes_csv
```

The CSV file should contain columns: DisplayName, NodeId, DataType

#### POST `/import_selected_csv`
Import a CSV file with pre-selected nodes:

```
# Example using curl
curl -X POST -F "file=@/path/to/selected.csv" http://localhost:8080/import_selected_csv
```

The CSV file should contain columns: DisplayName, NodeId, DataType

#### GET `/export_nodes_csv`
Download the current nodes.csv file:

```
curl -X GET http://localhost:8080/export_nodes_csv --output nodes.csv
```

#### GET `/export_selected_csv`
Download the current selected.csv file:

```
curl -X GET http://localhost:8080/export_selected_csv --output selected.csv
```

#### GET `/debug_selected_csv`
View the content of the selected.csv file as JSON:

```
curl -X GET http://localhost:8080/debug_selected_csv
```

Response:
```json
{
  "content": "DisplayName,NodeId,DataType\nDB15.R202_XTT610_Manteltemp,ns=2;s=DB15.R202_XTT610_Manteltemp,Float\n..."
}
```

#### POST `/update`
Update the list of selected nodes:

```
curl -X POST -H "Content-Type: application/json" -d '{"NodeIds": ["ns=2;s=DB15.R202_XTT610_Manteltemp", "ns=2;s=DB15.R201_XTT610_Manteltemp"]}' http://localhost:8080/update
```

Response:
```json
{
  "message": "Selection updated successfully",
  "selected_nodes": [
    {
      "DisplayName": "DB15.R202_XTT610_Manteltemp",
      "NodeId": "ns=2;s=DB15.R202_XTT610_Manteltemp",
      "DataType": "Float"
    },
    {
      "DisplayName": "DB15.R201_XTT610_Manteltemp",
      "NodeId": "ns=2;s=DB15.R201_XTT610_Manteltemp",
      "DataType": "Float"
    }
  ]
}
```

### Converter Controls

#### POST `/toggle_opcua_to_mqtt`
Start or stop the OPC UA to MQTT converter:

```
curl -X POST http://localhost:8080/toggle_opcua_to_mqtt
```

Response:
```json
{
  "message": "OPC UA to MQTT converter started" 
}
```
or
```json
{
  "message": "OPC UA to MQTT converter stopped"
}
```

#### POST `/toggle_mqtt_to_influx`
Start or stop the MQTT to InfluxDB converter:

```
curl -X POST http://localhost:8080/toggle_mqtt_to_influx
```

Response: Similar to the toggle_opcua_to_mqtt endpoint

#### POST `/toggle_both_converters`
Start or stop both converters at once:

```
# To start both converters
curl -X POST -H "Content-Type: application/json" -d '{"turn_on": true}' http://localhost:8080/toggle_both_converters

# To stop both converters
curl -X POST -H "Content-Type: application/json" -d '{"turn_on": false}' http://localhost:8080/toggle_both_converters
```

Response:
```json
{
  "message": "Both converters turned on"
}
```
or
```json
{
  "message": "Both converters turned off"
}
```

#### POST `/update_read_interval`
Update the OPC UA server polling interval:

```
curl -X POST -H "Content-Type: application/json" -d '{"interval": 10}' http://localhost:8080/update_read_interval
```

Response:
```json
{
  "message": "Read interval updated to 10 seconds"
}
```

### System Operations

#### POST `/clear_logs`
Clear all log files:

```
curl -X POST http://localhost:8080/clear_logs
```

Response:
```json
{
  "message": "All logs cleared successfully"
}
```

#### GET `/test_mqtt`
Test the connection to the MQTT broker:

```
curl -X GET http://localhost:8080/test_mqtt
```

Response:
```json
{
  "message": "MQTT connection successful"
}
```

#### GET `/get_latest_logs`
Get the latest log entries for all components:

```
curl -X GET http://localhost:8080/get_latest_logs
```

Response:
```json
{
  "Application": [
    "2025-04-12 15:30:45 - INFO - OPC UA to MQTT converter started",
    "2025-04-12 15:30:40 - INFO - Selection updated. Selected nodes: ns=2;s=DB15.R202_XTT610_Manteltemp, ns=2;s=DB15.R201_XTT610_Manteltemp"
  ],
  "opcua_to_MQTT_Converter.py": [
    "[2025-04-12 15:30:45] opcua_to_MQTT_Converter.py: Connected to MQTT Broker",
    "[2025-04-12 15:30:46] opcua_to_MQTT_Converter.py: Connected to OPC UA server"
  ],
  "mqtt_to_Influx_Converter.py": [
    "[2025-04-12 15:25:30] mqtt_to_Influx_Converter.py: Connecting to MQTT Broker...",
    "[2025-04-12 15:25:31] mqtt_to_Influx_Converter.py: Connected to MQTT Broker"
  ]
}
```

#### GET `/converter_status`
Get the current status of both converters:

```
curl -X GET http://localhost:8080/converter_status
```

Response:
```json
{
  "opcua_to_mqtt": "running",
  "mqtt_to_influx": "stopped"
}
```

## Example Workflow

1. Browse to the home page (`/`) to check the system status
2. Visit the node selection page (`/node_selection`) to choose which OPC UA nodes to monitor
3. Select nodes and click "Update Selection" to save your choices
4. Start both converters using the "Turn On Both Converters" button or `/toggle_both_converters` API
5. Check the logs page (`/logs`) to monitor data flow
6. Use Grafana or other tools connected to your InfluxDB to visualize the data
