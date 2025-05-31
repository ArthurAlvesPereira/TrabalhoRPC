import grpc
import time
from concurrent import futures
import threading

import heartbeat_pb2
import heartbeat_pb2_grpc

HEARTBEAT_LOG_FILE = "heartbeat.txt"

monitored_services = {}
service_lock = threading.Lock()

HEARTBEAT_EXPECTED_INTERVAL = 5

INACTIVITY_THRESHOLD = 2.5 * HEARTBEAT_EXPECTED_INTERVAL

class HeartbeatService(heartbeat_pb2_grpc.HeartbeatServicer):
    def SendHeartbeat(self, request, context):
        service_id = request.service_id
        current_time = time.time()

        with service_lock:
            monitored_services[service_id] = current_time

        print(f"Received heartbeat from {service_id} at {current_time}")

        with open(HEARTBEAT_LOG_FILE, "a") as log_file:
            log_file.write(f"{service_id} {current_time}\n")

        return heartbeat_pb2.EmptyResponse()
    
def monitor_services():
    while True:
        current_time = time.time()
        with service_lock:
            for service_id, last_heartbeat in list(monitored_services.items()):
                if current_time - last_heartbeat > INACTIVITY_THRESHOLD:
                    print(f"Service {service_id} is inactive. Last heartbeat at {last_heartbeat}")
                    del monitored_services[service_id]
        time.sleep(HEARTBEAT_EXPECTED_INTERVAL)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    heartbeat_pb2_grpc.add_HeartbeatServicer_to_server(HeartbeatService(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("Heartbeat server started on port 50051")
    
    try:
        monitor_thread = threading.Thread(target=monitor_services, daemon=True)
        monitor_thread.start()
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Server shutting down...")
        server.stop(0)
        
if __name__ == '__main__':
    serve()