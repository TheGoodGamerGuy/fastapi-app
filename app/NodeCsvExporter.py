import asyncio
# import csv
import logging
import time
from asyncio import Queue
from typing import List
from asyncua import Client, ua
import pandas as pd
# from io import StringIO

class NodeCSVExporter:
    def __init__(self, server_url: str, output_file: str, namespace_filter: int = 2):
        self.server_url = server_url
        self.output_file = output_file
        self.namespace_filter = namespace_filter
        self.nodes: List[ua.Node] = []
        self.client: Client = None
        self.node_queue: Queue = Queue()
        self.start_time = time.time()

    async def start_node_browse(self, rootnode):
        await self.node_queue.put(rootnode)
        total_processed = 0
        processed_nodes = set()
        while not self.node_queue.empty():
            batch = []
            for _ in range(min(100, self.node_queue.qsize())):
                if not self.node_queue.empty():
                    node = await self.node_queue.get()
                    if node not in processed_nodes:
                        batch.append(node)
                        processed_nodes.add(node)

            self.nodes.extend(batch)
            total_processed += len(batch)

            children_tasks = [node.get_children(refs=33) for node in batch]
            children_results = await asyncio.gather(*children_tasks)

            for children in children_results:
                for child in children:
                    if child not in processed_nodes:
                        await self.node_queue.put(child)

            for _ in batch:
                self.node_queue.task_done()

            elapsed_time = time.time() - self.start_time
            nodes_per_second = total_processed / elapsed_time if elapsed_time > 0 else 0
            print(f"\rNodes browsed: {total_processed}, Queue size: {self.node_queue.qsize()}, "
                f"Speed: {nodes_per_second:.2f} nodes/s", end="", flush=True)

        print(f"\nTotal nodes browsed: {total_processed}")
        self.nodes = list(processed_nodes)

    async def export_csv(self):
        all_nodes = self.nodes
        print(f"Total nodes: {len(all_nodes)}")
        nodes = [node for node in all_nodes if node.nodeid.NamespaceIndex == self.namespace_filter]
        total_nodes = len(nodes)
        filtered_out = len(all_nodes) - total_nodes
        print(f"Nodes after filtering: {total_nodes}")
        print(f"Nodes filtered by namespace: {filtered_out}")

        async def process_node(node):
            try:
                return await self.node_to_csv(node)
            except Exception as e:
                logging.error(f"Failed to export node {node.nodeid}: {e}")
                return None

        batch_size = 1000
        data = []
        start_time = time.time()
        processed = 0

        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i+batch_size]
            results = await asyncio.gather(*[process_node(node) for node in batch])
            data.extend([r for r in results if r])
            processed += len(batch)
            
            elapsed_time = time.time() - start_time
            nodes_per_second = processed / elapsed_time if elapsed_time > 0 else 0
            
            print(f"\rNodes exported: {processed}/{total_nodes}, "
                  f"Speed: {nodes_per_second:.2f} nodes/s", end="", flush=True)

        print("\nCreating DataFrame...")
        df = pd.DataFrame(data, columns=["NodeId", "BrowseName", "ParentNodeId", "DataType", "DisplayName", "Description"])
        
        print("Writing to CSV...")
        df.to_csv(self.output_file, index=False)

        print(f"\nExport completed.")
        print(f"Total nodes: {len(all_nodes)}")
        print(f"Nodes filtered by namespace: {filtered_out}")
        print(f"Nodes exported: {total_nodes}")



    async def node_to_csv(self, node):
        nodeid = node.nodeid.to_string()
        attributes = await node.read_attributes([
            ua.AttributeIds.BrowseName,
            ua.AttributeIds.DataType,
            ua.AttributeIds.DisplayName,
            ua.AttributeIds.Description
        ])
        
        browsename = attributes[0].Value.Value.Name if attributes[0].StatusCode.is_good() else "N/A"
        datatype_node = attributes[1].Value.Value if attributes[1].StatusCode.is_good() else None
        displayname = attributes[2].Value.Value.Text if attributes[2].StatusCode.is_good() else "N/A"
        description = attributes[3].Value.Value.Text if attributes[3].StatusCode.is_good() else "N/A"

        parent = await node.get_parent()
        parent_nodeid = parent.nodeid.to_string() if parent else "N/A"

        # Get the actual datatype name
        if datatype_node:
            try:
                datatype_node = self.client.get_node(datatype_node)
                datatype = await datatype_node.read_browse_name()
                datatype = datatype.Name
            except Exception:
                datatype = str(datatype_node)
        else:
            datatype = "N/A"

        return [nodeid, browsename, parent_nodeid, datatype, displayname, description]

    async def import_nodes(self):
        self.client = Client(self.server_url)
        await self.client.connect()
        print("Connected to OPC UA server")
        print("Browsing nodes...")
        root = self.client.get_root_node()
        await self.start_node_browse(root)

async def main():
    logging.basicConfig(level=logging.WARNING)
    exporter = NodeCSVExporter("opc.tcp://100.94.111.58:4841", "nodes_output.csv")
    try:
        await exporter.import_nodes()
        await exporter.export_csv()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if exporter.client:
            await exporter.client.disconnect()
            print("Disconnected from OPC UA server")

if __name__ == "__main__":
    asyncio.run(main())