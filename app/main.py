from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
import csv
import os
import logging
import asyncio
import paho.mqtt.client as mqtt
from datetime import datetime
from .NodeCsvExporter import NodeCSVExporter  # Import the NodeCSVExporter class
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
import tempfile
# from fastapi.background import BackgroundTask
from starlette.background import BackgroundTask

LOG_FILE = "app/logs/application.log"
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

OPCUA_SERVER_URL = "opc.tcp://100.94.111.58:4841"

NODES_CSV = "app/data/nodes.csv"
SELECTED_CSV = "app/data/selected.csv"
NODES_OUTPUT_CSV = "app/data/nodes_output.csv"

OPCUA_TO_MQTT_LOG_FILE = "app/logs/opcua_to_mqtt.log"
MQTT_TO_INFLUX_LOG_FILE = "app/logs/mqtt_to_influx.log"
OPCUA_TO_MQTT_SCRIPT = "app/opcua_to_MQTT_Converter.py"
MQTT_TO_INFLUX_SCRIPT = "app/mqtt_to_Influx_Converter.py"


opcua_to_mqtt_process = None
mqtt_to_influx_process = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.debug("Startup event called")  # This should go to the log file
    # os.makedirs("app/logs", exist_ok=True)
    # logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    await run_node_csv_exporter()     # UNCOMMENT FOR PRODUCTION
    create_nodes_csv_from_nodes_output()
    yield
    # shutdown event

app = FastAPI(lifespan=lifespan)
    
async def run_node_csv_exporter():
    server_url = OPCUA_SERVER_URL
    exporter = NodeCSVExporter(server_url, NODES_OUTPUT_CSV)
    try:
        await exporter.import_nodes()
        await exporter.export_csv()
    except Exception as e:
        logging.error(f"Error in node CSV export: {e}")
    finally:
        if exporter.client:
            await exporter.client.disconnect()

def create_nodes_csv_from_nodes_output():
    with open(NODES_OUTPUT_CSV, mode='r') as input_file, open(NODES_CSV, mode='w', newline='') as output_file:
        reader = csv.DictReader(input_file)
        writer = csv.writer(output_file)
        writer.writerow(["DisplayName", "NodeId", "DataType"])
        for row in reader:
            writer.writerow([row['DisplayName'], row['NodeId'], row['DataType']])
    logging.info(f"Created {NODES_CSV} from {NODES_OUTPUT_CSV}")

@app.post("/import_nodes_csv")
async def import_nodes_csv(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        with open(NODES_CSV, "wb") as f:
            f.write(contents)
        return {"message": "nodes.csv imported successfully"}
    except Exception as e:
        logging.error(f"Error importing nodes.csv: {e}")
        raise HTTPException(status_code=500, detail="Failed to import nodes.csv")

@app.post("/import_selected_csv")
async def import_selected_csv(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        with open(SELECTED_CSV, "wb") as f:
            f.write(contents)
        if is_process_running(OPCUA_TO_MQTT_SCRIPT):
            stop_script(OPCUA_TO_MQTT_SCRIPT)
            await asyncio.sleep(1)
            await start_script(OPCUA_TO_MQTT_SCRIPT)
            logging.info("OPC UA to MQTT converter restarted with new node selection")
        return {"message": "selected.csv imported successfully"}
    except Exception as e:
        logging.error(f"Error importing selected.csv: {e}")
        raise HTTPException(status_code=500, detail="Failed to import selected.csv")

@app.get("/export_nodes_csv")
async def export_nodes_csv():
    return FileResponse(NODES_CSV, filename="nodes.csv")

@app.get("/export_selected_csv")
async def export_selected_csv():
    try:
        # Ensure we're reading the most recent version of the file
        with open(SELECTED_CSV, 'r') as file:
            content = file.read()
        
        # Create a temporary file with the current content
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        # Use the temporary file for the response
        return FileResponse(temp_path, filename="selected.csv", background=BackgroundTask(lambda: os.unlink(temp_path)))
    except Exception as e:
        logging.error(f"Error exporting selected.csv: {e}")
        raise HTTPException(status_code=500, detail="Failed to export selected.csv")

@app.get("/debug_selected_csv")
async def debug_selected_csv():
    try:
        file_path = os.path.abspath(SELECTED_CSV)
        logging.info(f"Attempting to read file: {file_path}")
        
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            raise HTTPException(status_code=404, detail="Selected CSV file not found")
        
        with open(file_path, 'r') as file:
            content = file.read()
        logging.info(f"File content (first 100 chars): {content[:100]}")
        return {"content": content}
    except Exception as e:
        logging.error(f"Error reading selected CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read selected CSV: {str(e)}")

class Node(BaseModel):
    NodeId: str
    description: str

class UpdateRequest(BaseModel):
    NodeIds: list[str] = []

class IntervalUpdate(BaseModel):
    interval: int

class ConverterToggle(BaseModel):
    turn_on: bool

async def run_script(script_name):
    global opcua_to_mqtt_process, mqtt_to_influx_process
    log_file_path = OPCUA_TO_MQTT_LOG_FILE if script_name == OPCUA_TO_MQTT_SCRIPT else MQTT_TO_INFLUX_LOG_FILE
    process = await asyncio.create_subprocess_exec('python3', script_name, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    if script_name == OPCUA_TO_MQTT_SCRIPT: opcua_to_mqtt_process = process
    elif script_name == MQTT_TO_INFLUX_SCRIPT: mqtt_to_influx_process = process
    while True:
        line = await process.stdout.readline()
        if not line: break
        with open(log_file_path, 'a') as log_file:
            log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {script_name}: {line.decode().strip()}\n")
    error = await process.stderr.read()
    if error:
        with open(log_file_path, 'a') as log_file:
            log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {script_name} Error: {error.decode().strip()}\n")
    await process.wait()

def is_process_running(script_name):
    return (opcua_to_mqtt_process if script_name == OPCUA_TO_MQTT_SCRIPT else mqtt_to_influx_process) is not None and (opcua_to_mqtt_process if script_name == OPCUA_TO_MQTT_SCRIPT else mqtt_to_influx_process).returncode is None

async def start_script(script_name):
    if not is_process_running(script_name):
        asyncio.create_task(run_script(script_name))
        return True
    return False

def stop_script(script_name):
    global opcua_to_mqtt_process, mqtt_to_influx_process
    process = opcua_to_mqtt_process if script_name == OPCUA_TO_MQTT_SCRIPT else mqtt_to_influx_process
    if process:
        process.terminate()
        if script_name == OPCUA_TO_MQTT_SCRIPT: opcua_to_mqtt_process = None
        else: mqtt_to_influx_process = None
        return True
    return False

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        # with open(NODES_CSV, mode='r') as file:
        #     nodes = [{"NodeId": row['NodeId'], "display_name": row['display_name']} for row in csv.DictReader(file)]
        # with open(SELECTED_CSV, mode='r') as file:
        #     selected = {row['NodeId'] for row in csv.DictReader(file)}

        opcua_to_mqtt_status = "running" if is_process_running(OPCUA_TO_MQTT_SCRIPT) else "stopped"
        mqtt_to_influx_status = "running" if is_process_running(MQTT_TO_INFLUX_SCRIPT) else "stopped"
    except Exception as e:
        logging.error(f"Error reading CSV files or getting converter status: {e}")
        # nodes, selected = [], set()
        opcua_to_mqtt_status = mqtt_to_influx_status = "unknown"
    return templates.TemplateResponse("index.html", {
        "request": request,
        # "nodes": nodes,
        # "selected": selected,
        "opcua_to_mqtt_status": opcua_to_mqtt_status,
        "mqtt_to_influx_status": mqtt_to_influx_status,
        "read_interval": os.environ.get('READ_INTERVAL', '5')
    })

# @app.post("/add_node")
# async def add_node(NodeId: str = Form(...), display_name: str = Form(...)):
#     try:
#         with open(NODES_CSV, mode='a', newline='') as file:
#             csv.writer(file).writerow([NodeId, display_name])
#         logging.info(f"Added new node: {NodeId} - {display_name}")
#         return JSONResponse(content={"message": "Node added successfully", "node": {"NodeId": NodeId, "display_name": display_name}})
#     except Exception as e:
#         logging.error(f"Error adding node: {e}")
#         return JSONResponse(content={"error": "Failed to add node"}, status_code=500)

@app.post("/update")
async def update_selected(request: UpdateRequest):
    try:
        with open(NODES_CSV, mode='r') as file:
            all_nodes = [row for row in csv.DictReader(file)]
        selected_nodes = [node for node in all_nodes if node['NodeId'] in request.NodeIds]
        with open(SELECTED_CSV, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=["DisplayName", "NodeId", "DataType"])
            writer.writeheader()
            writer.writerows(selected_nodes)
        if is_process_running(OPCUA_TO_MQTT_SCRIPT):
            stop_script(OPCUA_TO_MQTT_SCRIPT)
            await asyncio.sleep(1)
            await start_script(OPCUA_TO_MQTT_SCRIPT)
            logging.info("OPC UA to MQTT converter restarted with new node selection")
        logging.info(f"Selection updated. Selected nodes: {', '.join(request.NodeIds)}" if request.NodeIds else "Selection updated. No nodes selected.")
        return JSONResponse(content={"message": "Selection updated successfully" if request.NodeIds else "All nodes deselected", "selected_nodes": selected_nodes})
    except Exception as e:
        logging.error(f"Error updating selection: {e}")
        return JSONResponse(content={"error": "Failed to update selection"}, status_code=500)

@app.post("/clear_logs")
async def clear_logs():
    try:
        for log_file in [LOG_FILE, OPCUA_TO_MQTT_LOG_FILE, MQTT_TO_INFLUX_LOG_FILE]:
            open(log_file, 'w').close()
        return {"message": "All logs cleared successfully"}
    except Exception as e:
        logging.error(f"Error clearing logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear logs")

@app.post("/toggle_opcua_to_mqtt")
async def toggle_opcua_to_mqtt():
    if is_process_running(OPCUA_TO_MQTT_SCRIPT):
        if stop_script(OPCUA_TO_MQTT_SCRIPT):
            logging.info("OPC UA to MQTT converter stopped")
            return {"message": "OPC UA to MQTT converter stopped"}
        else:
            logging.error("Failed to stop OPC UA to MQTT converter")
            return JSONResponse(content={"error": "Failed to stop converter"}, status_code=500)
    else:
        if await start_script(OPCUA_TO_MQTT_SCRIPT):
            logging.info("OPC UA to MQTT converter started")
            return {"message": "OPC UA to MQTT converter started"}
        else:
            logging.error("Failed to start OPC UA to MQTT converter")
            return JSONResponse(content={"error": "Failed to start converter"}, status_code=500)

@app.post("/toggle_mqtt_to_influx")
async def toggle_mqtt_to_influx():
    if is_process_running(MQTT_TO_INFLUX_SCRIPT):
        if stop_script(MQTT_TO_INFLUX_SCRIPT):
            logging.info("MQTT to InfluxDB converter stopped")
            return {"message": "MQTT to InfluxDB converter stopped"}
        else:
            logging.error("Failed to stop MQTT to InfluxDB converter")
            return JSONResponse(content={"error": "Failed to stop converter"}, status_code=500)
    else:
        if await start_script(MQTT_TO_INFLUX_SCRIPT):
            logging.info("MQTT to InfluxDB converter started")
            return {"message": "MQTT to InfluxDB converter started"}
        else:
            logging.error("Failed to start MQTT to InfluxDB converter")
            return JSONResponse(content={"error": "Failed to start converter"}, status_code=500)

@app.get("/logs", response_class=HTMLResponse)
async def get_logs(request: Request):
    log_files = {"Application": LOG_FILE, "opcua_to_MQTT_Converter.py": OPCUA_TO_MQTT_LOG_FILE, "mqtt_to_Influx_Converter.py": MQTT_TO_INFLUX_LOG_FILE}
    logs = {}
    for script, log_file in log_files.items():
        try:
            with open(log_file, mode="r") as file:
                logs[script] = file.readlines()
        except Exception as e:
            logs[script] = [f"Error reading log file: {e}\n"]
    return templates.TemplateResponse("logs.html", {"request": request, "logs": logs})

@app.get("/converter_status")
async def get_converter_status():
    return {"opcua_to_mqtt": "running" if is_process_running(OPCUA_TO_MQTT_SCRIPT) else "stopped", "mqtt_to_influx": "running" if is_process_running(MQTT_TO_INFLUX_SCRIPT) else "stopped"}

@app.get("/test_mqtt")
async def test_mqtt():
    try:
        client = mqtt.Client()
        client.connect("host.docker.internal", 1883, 60)
        client.disconnect()
        connection_status = True
    except Exception as e:
        logging.error(f"MQTT connection test failed: {e}")
        connection_status = False
    if connection_status:
        logging.info("MQTT connection successful")
        return {"message": "MQTT connection successful"}
    else:
        logging.error("MQTT connection failed")
        return JSONResponse(content={"error": "MQTT connection failed"}, status_code=500)

@app.get("/get_latest_logs")
async def get_latest_logs():
    log_files = {"Application": LOG_FILE, "opcua_to_MQTT_Converter.py": OPCUA_TO_MQTT_LOG_FILE, "mqtt_to_Influx_Converter.py": MQTT_TO_INFLUX_LOG_FILE}
    latest_logs = {}
    for script, log_file in log_files.items():
        try:
            with open(log_file, mode="r") as file:
                latest_logs[script] = file.readlines()[-100:][::-1]
        except Exception as e:
            latest_logs[script] = [f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error reading log file: {e}\n"]
    return latest_logs

@app.post("/update_read_interval")
async def update_read_interval(update: IntervalUpdate):
    os.environ['READ_INTERVAL'] = str(update.interval)
    if is_process_running(OPCUA_TO_MQTT_SCRIPT):
        stop_script(OPCUA_TO_MQTT_SCRIPT)
        await asyncio.sleep(1)
        await start_script(OPCUA_TO_MQTT_SCRIPT)
        logging.info(f"Read interval updated to {update.interval} seconds and OPC UA to MQTT converter restarted")
        return {"message": f"Read interval updated to {update.interval} seconds and OPC UA to MQTT converter restarted"}
    logging.info(f"Read interval updated to {update.interval} seconds")
    return {"message": f"Read interval updated to {update.interval} seconds"}

@app.post("/toggle_both_converters")
async def toggle_both_converters(toggle: ConverterToggle):
    opcua_running = is_process_running(OPCUA_TO_MQTT_SCRIPT)
    mqtt_running = is_process_running(MQTT_TO_INFLUX_SCRIPT)

    if toggle.turn_on:
        if not opcua_running:
            await start_script(OPCUA_TO_MQTT_SCRIPT)
        if not mqtt_running:
            await start_script(MQTT_TO_INFLUX_SCRIPT)
        message = "Both converters turned on"
    else:
        if opcua_running:
            stop_script(OPCUA_TO_MQTT_SCRIPT)
        if mqtt_running:
            stop_script(MQTT_TO_INFLUX_SCRIPT)
        message = "Both converters turned off"

    logging.info(message)
    return {"message": message}

@app.get("/node_selection", response_class=HTMLResponse)
async def node_selection(request: Request):
    try:
        with open(NODES_CSV, mode='r') as file:
            nodes = [row for row in csv.DictReader(file)]
        with open(SELECTED_CSV, mode='r') as file:
            selected = {row['NodeId'] for row in csv.DictReader(file)}
    except Exception as e:
        logging.error(f"Error reading CSV files: {e}")
        nodes, selected = [], set()
    return templates.TemplateResponse("node_selection.html", {
        "request": request,
        "nodes": nodes,
        "selected": selected
    })