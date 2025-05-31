# backup_server.py

import grpc
import time
from concurrent import futures
import threading

# Módulos gerados para o serviço de backup
import backup_pb2
import backup_pb2_grpc

# Módulos gerados para o cliente de heartbeat
import heartbeat_pb2
import heartbeat_pb2_grpc

BACKUP_LOG_FILE = "Backup.txt"
BACKUP_SERVER_ID = "backup_server_main" # ID para o heartbeat
HEARTBEAT_SERVER_ADDRESS = 'localhost:50051' # Endereço do seu servidor de heartbeat
HEARTBEAT_SEND_INTERVAL = 4 # Segundos

backup_log_lock = threading.Lock() # Para escrita segura no arquivo de log

class BackupServicer(backup_pb2_grpc.BackupServiceServicer):
    def LogTransaction(self, request, context):
        terminal_id = request.terminal_id
        vehicle_class = request.vehicle_class
        vehicle_name = request.vehicle_name
        status = request.status
        
        # Timestamp gerado pelo servidor de backup no momento do recebimento
        current_time_str = time.ctime(time.time())
        
        log_entry = (f"Requisição recebida do terminal {terminal_id} para classe {vehicle_class} "
                     f"{vehicle_name} {status} em {current_time_str}\n") # [cite: 10]
        
        try:
            with backup_log_lock:
                with open(BACKUP_LOG_FILE, "a") as f:
                    f.write(log_entry)
            print(f"LOG Backup: {log_entry.strip()}") # Debug
            return backup_pb2.TransactionResponse(success=True, message="Log registrado com sucesso.")
        except Exception as e:
            print(f"Erro ao escrever no log de backup: {e}")
            return backup_pb2.TransactionResponse(success=False, message=f"Erro ao registrar log: {e}")

def send_heartbeats_to_master(server_id, hb_server_address, interval):
    while True:
        try:
            with grpc.insecure_channel(hb_server_address) as channel:
                stub = heartbeat_pb2_grpc.HeartbeatStub(channel)
                # print(f"Servidor de Backup ({server_id}) conectado ao Heartbeat Master em {hb_server_address}")
                while True:
                    hb_request = heartbeat_pb2.HeartbeatRequest(service_id=server_id)
                    stub.SendHeartbeat(hb_request)
                    # print(f"[{time.ctime()}] Heartbeat enviado de {server_id} para o Master")
                    time.sleep(interval)
        except grpc.RpcError as e:
            print(f"Servidor de Backup ({server_id}): Erro RPC ao enviar heartbeat - {e.code()}: {e.details()}. Tentando reconectar...")
        except Exception as e:
            print(f"Servidor de Backup ({server_id}): Erro inesperado no envio de heartbeat: {e}. Tentando reconectar...")
        time.sleep(interval) # Espera antes de tentar recriar o canal

def serve():
    # Iniciar thread de heartbeat para este servidor de backup
    hb_thread = threading.Thread(
        target=send_heartbeats_to_master,
        args=(BACKUP_SERVER_ID, HEARTBEAT_SERVER_ADDRESS, HEARTBEAT_SEND_INTERVAL),
        daemon=True
    )
    hb_thread.start()

    # Configurar e iniciar o servidor gRPC para o serviço de Backup
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    backup_pb2_grpc.add_BackupServiceServicer_to_server(BackupServicer(), server)
    
    backup_server_port = "50051" # Escolha uma porta DIFERENTE da do heartbeat server
    server.add_insecure_port(f'[::]:{backup_server_port}')
    print(f"Servidor de Backup iniciado na porta {backup_server_port}, enviando heartbeats como '{BACKUP_SERVER_ID}'.")
    
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Servidor de Backup encerrado.")
        server.stop(0)

if __name__ == '__main__':
    serve()
    