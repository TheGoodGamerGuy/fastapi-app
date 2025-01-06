import asyncio
import logging
import time
from asyncio import Queue
from typing import List
from asyncua import Client, ua
import pandas as pd

class NodeCSVExporter:
    def __init__(self, server_url: str, output_file: str, namespace_filter: int = 2, print_callback=None):
        self.server_url = server_url
        self.output_file = output_file
        self.namespace_filter = namespace_filter
        self.nodes: List[ua.Node] = []
        self.client: Client = None
        self.node_queue: Queue = Queue()
        self.start_time = time.time()
        self.print_callback = print_callback

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

            children_tasks = [node.get_children() for node in batch]
            children_results = await asyncio.gather(*children_tasks)

            for children in children_results:
                for child in children:
                    if child not in processed_nodes:
                        await self.node_queue.put(child)

            for _ in batch:
                self.node_queue.task_done()

            elapsed_time = time.time() - self.start_time
            nodes_per_second = total_processed / elapsed_time if elapsed_time > 0 else 0
            message = f"Nodes browsed: {total_processed}, Queue size: {self.node_queue.qsize()}, Speed: {nodes_per_second:.2f} nodes/s"
            if self.print_callback:
                self.print_callback(message)

        final_message = f"Total nodes browsed: {total_processed}"
        if self.print_callback:
            self.print_callback(final_message)
        self.nodes = list(processed_nodes)

    async def node_to_csv(self, node):
        try:
            browse_name = await node.read_browse_name()
            display_name = await node.read_display_name()
            node_class = await node.read_node_class()
            description = await node.read_description()
            data_type = None
            if node_class == ua.NodeClass.Variable:
                data_type = await node.read_data_type()
                data_type = str(data_type)
            parent = await node.get_parent()
            parent_id = parent.nodeid.to_string() if parent else None
            return [
                node.nodeid.to_string(),
                browse_name.to_string(),
                parent_id,
                data_type,
                display_name.Text,
                description.Text if description else None
            ]
        except Exception as e:
            logging.error(f"Error processing node {node.nodeid}: {e}")
            return None

    async def export_csv(self):
        all_nodes = self.nodes
        nodes = [node for node in all_nodes if node.nodeid.NamespaceIndex == self.namespace_filter]
        total_nodes = len(nodes)
        filtered_out = len(all_nodes) - total_nodes

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
            
            message = f"Nodes exported: {processed}/{total_nodes}, Speed: {nodes_per_second:.2f} nodes/s"
            if self.print_callback:
                self.print_callback(message)

        df = pd.DataFrame(data, columns=["NodeId", "BrowseName", "ParentNodeId", "DataType", "DisplayName", "Description"])
        df.to_csv(self.output_file, index=False)

        final_message = f"Export completed. Total nodes: {len(all_nodes)}, Filtered out: {filtered_out}, Exported: {total_nodes}"
        if self.print_callback:
            self.print_callback(final_message)

    async def import_nodes(self):
        self.client = Client(self.server_url)
        await self.client.connect()
        message = "Connected to OPC UA server\nBrowsing nodes..."
        if self.print_callback:
            self.print_callback(message)
        else:
            print(message)
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