# heartbeat_server.py

import grpc
import time
from concurrent import futures
import threading

# Assume que heartbeat_pb2.py e heartbeat_pb2_grpc.py
# foram gerados a partir do protos/heartbeat.proto e estão na mesma pasta
import heartbeat_pb2
import heartbeat_pb2_grpc

HEARTBEAT_LOG_FILE = "heartbeat.txt" # [cite: 1]

# Estrutura para armazenar o último timestamp e o status de cada serviço
# Ex: monitored_services = {"terminal_1": {"last_seen": 1678886400.0, "status": "ativo"}}
monitored_services = {}
service_lock = threading.Lock() # Lock para acesso seguro ao dicionário

HEARTBEAT_EXPECTED_INTERVAL = 5  # Intervalo esperado entre heartbeats em segundos [cite: 1]
# Se não recebermos um heartbeat em 2.5x o intervalo, consideramos inativo.
INACTIVITY_THRESHOLD = HEARTBEAT_EXPECTED_INTERVAL * 2.5 # [cite: 1]

class HeartbeatServicer(heartbeat_pb2_grpc.HeartbeatServicer): # Nome da classe pode ser HeartbeatService como no seu
    def SendHeartbeat(self, request, context):
        service_id = request.service_id
        current_time = time.time()
        current_time_str = time.ctime(current_time)

        with service_lock:
            previous_status = monitored_services.get(service_id, {}).get('status')
            monitored_services[service_id] = {'last_seen': current_time, 'status': 'ativo'}

            # Loga a transição para ativo ou a primeira aparição no formato esperado
            if previous_status != 'ativo':
                log_message = f"{service_id} está ativo, última mensagem recebida em {current_time_str}\n" # [cite: 1]
                print(f"LOG Heartbeat: {log_message.strip()}")
                with open(HEARTBEAT_LOG_FILE, "a") as f:
                    f.write(log_message)
            else:
                # Se já estava ativo, apenas atualizamos o timestamp.
                # Opcionalmente, você poderia logar cada heartbeat recebido aqui,
                # mas a especificação do log do heartbeat sugere logar o estado/transição.
                # A especificação do log para o arquivo heartbeat.txt é:
                # "Terminal X está ativo, última mensagem recebida em [timestamp]"
                # "Servidor de Backup está ativo, última mensagem recebida em [timestamp]"
                # "Terminal X está inativo, última mensagem recebida em [timestamp]"
                # "Servidor de Backup está inativo, última mensagem recebida em [timestamp]"
                # Para cumprir isso estritamente a cada heartbeat, mesmo que já ativo:
                log_message_periodic_active = f"{service_id} está ativo, última mensagem recebida em {current_time_str}\n"
                # Para evitar logs excessivos, pode-se optar por não logar a cada batida se já ativo.
                # A implementação atual foca em logar a *transição* para ativo e a *transição* para inativo.
                # E também a primeira vez que o serviço é visto.
                # Se o requisito é logar *sempre* o status ativo em cada batida, descomente a escrita abaixo.
                # print(f"LOG Heartbeat (já ativo): {log_message_periodic_active.strip()}")
                # with open(HEARTBEAT_LOG_FILE, "a") as f:
                #     f.write(log_message_periodic_active)
                pass


        # print(f"Received heartbeat from {service_id} at {current_time_str}") # Saída do seu código original
        return heartbeat_pb2.EmptyResponse()

def monitor_services():
    while True:
        time.sleep(HEARTBEAT_EXPECTED_INTERVAL) # Verifica periodicamente
        current_time = time.time()
        
        with service_lock:
            for service_id, data in list(monitored_services.items()): # Usar list() para iterar sobre uma cópia
                if data['status'] == 'ativo': # Só verifica inatividade se estiver atualmente ativo
                    if current_time - data['last_seen'] > INACTIVITY_THRESHOLD:
                        # Serviço tornou-se inativo
                        monitored_services[service_id]['status'] = 'inativo'
                        # Usa o timestamp da ÚLTIMA MENSAGEM ATIVA para o log de inatividade
                        log_timestamp_str = time.ctime(data['last_seen']) 
                        log_message = f"{service_id} está inativo, última mensagem recebida em {log_timestamp_str}\n" # [cite: 1]
                        print(f"LOG Heartbeat: {log_message.strip()}")
                        with open(HEARTBEAT_LOG_FILE, "a") as f:
                            f.write(log_message)
                # Não é necessário remover explicitamente com 'del' se você apenas atualiza o status.
                # Se um serviço inativo enviar um novo heartbeat, ele será marcado como 'ativo' novamente.

def serve():
    # Limpar o log antigo ao iniciar (opcional, mas bom para testes limpos)
    # Pode comentar esta parte se quiser manter o histórico entre execuções
    with open(HEARTBEAT_LOG_FILE, "w") as f:
        f.write(f"{time.ctime(time.time())}: Log do Servidor de Heartbeat iniciado.\n")
        
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    # Use o nome da sua classe Servicer aqui (HeartbeatService ou HeartbeatServicer)
    heartbeat_pb2_grpc.add_HeartbeatServicer_to_server(HeartbeatServicer(), server) # [cite: 1]
    
    server_port = '50050' # Porta confirmada por você
    server.add_insecure_port(f'[::]:{server_port}')
    server.start()
    print(f"Heartbeat server started on port {server_port}")

    monitor_thread = threading.Thread(target=monitor_services, daemon=True)
    monitor_thread.start()
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Heartbeat Server shutting down...")
        server.stop(0)
        
if __name__ == '__main__':
    serve()