# heartbeat_server.py

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
INACTIVITY_THRESHOLD = HEARTBEAT_EXPECTED_INTERVAL * 2.5

class HeartbeatServicer(heartbeat_pb2_grpc.HeartbeatServicer):
    def SendHeartbeat(self, request, context):
        service_id = request.service_id
        current_time = time.time()
        current_time_str = time.ctime(current_time)

        with service_lock:
            previous_status = monitored_services.get(service_id, {}).get('status')
            monitored_services[service_id] = {'last_seen': current_time, 'status': 'ativo'}

            if previous_status != 'ativo':
                log_message = f"{service_id} está ativo, última mensagem recebida em {current_time_str}\n"
                print(f"LOG Heartbeat: {log_message.strip()}")
                with open(HEARTBEAT_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(log_message)
        return heartbeat_pb2.EmptyResponse()

def monitor_services():
    while True:
        time.sleep(HEARTBEAT_EXPECTED_INTERVAL)
        current_time = time.time()
        
        with service_lock:
            for service_id, data in list(monitored_services.items()):
                if data['status'] == 'ativo':
                    if current_time - data['last_seen'] > INACTIVITY_THRESHOLD:
                        monitored_services[service_id]['status'] = 'inativo'
                        log_timestamp_str = time.ctime(data['last_seen']) 
                        log_message = f"{service_id} está inativo, última mensagem recebida em {log_timestamp_str}\n"
                        print(f"LOG Heartbeat: {log_message.strip()}")
                        with open(HEARTBEAT_LOG_FILE, "a", encoding="utf-8") as f:
                            f.write(log_message)

def serve():
    with open(HEARTBEAT_LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"{time.ctime(time.time())}: Log do Servidor de Heartbeat iniciado.\n")
        
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    heartbeat_pb2_grpc.add_HeartbeatServicer_to_server(HeartbeatServicer(), server)
    
    server_port = '50050'
    server.add_insecure_port(f'[::]:{server_port}')
    server.start()
    print(f"Heartbeat server started on port {server_port}")

    monitor_thread = threading.Thread(target=monitor_services, daemon=True)
    monitor_thread.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Heartbeat Server shutting down...")
    except Exception as e:
        print(f"Heartbeat Server encerrado devido a uma exceção: {e}")
    finally:
        if 'server' in locals() and server:
            server.stop(0)
        
if __name__ == '__main__':
    serve()
