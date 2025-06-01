# terminal_1.py

import grpc
import time
from concurrent import futures
import threading

import terminal_pb2
import terminal_pb2_grpc
import heartbeat_pb2 
import heartbeat_pb2_grpc 
import backup_pb2 
import backup_pb2_grpc 

TERMINAL_ID = "terminal_1"
TERMINAL_PORT = "50151" 
HEARTBEAT_SERVER_ADDRESS = 'localhost:50050'
BACKUP_SERVER_ADDRESS = 'localhost:50055' 
HEARTBEAT_SEND_INTERVAL = 5 
TERMINAL_LOG_FILE = f"terminal_{TERMINAL_ID}.txt"

FLEET = {
    "Executivos": [
        {"name": "BMW Série 5", "available": True, "rented_to_client_id": None},
        {"name": "Toyota Corolla Altis Híbrido", "available": True, "rented_to_client_id": None},
    ],
    "Minivans": [
        {"name": "Chevrolet Spin", "available": True, "rented_to_client_id": None},
        {"name": "Fiat Doblo", "available": True, "rented_to_client_id": None},
        {"name": "Nissan Livina", "available": True, "rented_to_client_id": None},
        {"name": "Citroën C4 Picasso", "available": True, "rented_to_client_id": None},
        {"name": "Chevrolet Zafira", "available": True, "rented_to_client_id": None},
    ]
}
POSSIBLE_CLASSES = ["Econômicos", "Intermediários", "SUV", "Executivos", "Minivans"]
for vc_class in POSSIBLE_CLASSES:
    if vc_class not in FLEET:
        FLEET[vc_class] = []

fleet_lock = threading.Lock() 
waiting_list = {} 
waiting_list_lock = threading.Lock()

def log_terminal_event(message):
    log_line = f"{time.ctime(time.time())}: {message}"
    print(f"LOG {TERMINAL_ID}: {message}")
    with open(TERMINAL_LOG_FILE, "a") as f:
        f.write(log_line + "\n")

def send_heartbeats_to_master(terminal_id, hb_server_address, interval):
    while True:
        try:
            with grpc.insecure_channel(hb_server_address) as channel:
                stub = heartbeat_pb2_grpc.HeartbeatStub(channel)
                while True:
                    hb_request = heartbeat_pb2.HeartbeatRequest(service_id=terminal_id)
                    stub.SendHeartbeat(hb_request)
                    time.sleep(interval)
        except Exception as e:
            log_terminal_event(f"Erro ao enviar heartbeat: {e}. Tentando reconectar...")
        time.sleep(interval) 

def process_waiting_list_for_class(vehicle_class_available):
    pending_client_info = None
    with waiting_list_lock:
        if vehicle_class_available in waiting_list and waiting_list[vehicle_class_available]:
            pending_client_info = waiting_list[vehicle_class_available].pop(0) 
            if not waiting_list[vehicle_class_available]:
                del waiting_list[vehicle_class_available]
        else:
            return 

    client_id = pending_client_info["client_id"]
    client_ip = pending_client_info["client_ip"]
    client_port = pending_client_info["client_port"]

    log_terminal_event(f"Tentando atender cliente {client_id} da lista de espera para classe {vehicle_class_available}.")

    assigned_vehicle_name = None
    with fleet_lock: 
        for vehicle in FLEET.get(vehicle_class_available, []):
            if vehicle["available"]:
                vehicle["available"] = False
                vehicle["rented_to_client_id"] = client_id
                assigned_vehicle_name = vehicle["name"]
                break
    
    if not assigned_vehicle_name:
        log_terminal_event(f"ERRO INTERNO: Veículo da classe {vehicle_class_available} deveria estar disponível para {client_id} da lista de espera, mas não foi encontrado. Repondo cliente na lista.")
        with waiting_list_lock:
            if vehicle_class_available not in waiting_list:
                waiting_list[vehicle_class_available] = []
            waiting_list[vehicle_class_available].insert(0, pending_client_info)
        return

    callback_success = False
    try:
        client_callback_address = f"{client_ip}:{client_port}"
        log_terminal_event(f"Tentando callback para {client_id} em {client_callback_address} para veículo {assigned_vehicle_name}...")
        with grpc.insecure_channel(client_callback_address) as channel:
            callback_stub = terminal_pb2_grpc.CallbackServiceStub(channel)
            callback_message_content = f"Seu veículo '{assigned_vehicle_name}' da classe '{vehicle_class_available}' está pronto!"
            cb_message = terminal_pb2.CallbackMessage(message_content=callback_message_content)
            cb_response = callback_stub.ReceiveCallback(cb_message, timeout=5) 
            if cb_response and cb_response.status == "Callback Recebido OK":
                log_terminal_event(f"Callback para {client_id} bem-sucedido: {cb_response.status}")
                callback_success = True
            else:
                log_terminal_event(f"Callback para {client_id} retornou status inesperado: {cb_response.status if cb_response else 'Sem resposta'}")
    except grpc.RpcError as e:
        log_terminal_event(f"Falha no callback para {client_id} ({client_callback_address}): {e.code()} - {e.details()}")
    except Exception as e:
        log_terminal_event(f"Exceção durante callback para {client_id}: {e}")

    log_terminal_event(f"Veículo {assigned_vehicle_name} alocado para {client_id} da lista de espera. Atualizando backup.")
    try:
        with grpc.insecure_channel(BACKUP_SERVER_ADDRESS) as channel:
            backup_stub = backup_pb2_grpc.BackupServiceStub(channel)
            backup_request = backup_pb2.TransactionRequest(
                terminal_id=TERMINAL_ID,
                vehicle_class=vehicle_class_available,
                vehicle_name=assigned_vehicle_name,
                status="CONCLUIDA" 
            )
            # Log para o terminal ANTES de enviar ao backup
            log_terminal_event(f"Requisição enviada ao servidor de backup para cliente {client_id}, classe {vehicle_class_available}, veículo '{assigned_vehicle_name}', status CONCLUIDA em {time.ctime(time.time())}")
            backup_response = backup_stub.LogTransaction(backup_request)
            if backup_response.success:
                # Log para o terminal DEPOIS de receber do backup
                log_terminal_event(f"Resposta recebida do servidor de backup (SUCESSO) para cliente {client_id}, classe {vehicle_class_available}, veículo '{assigned_vehicle_name}', status CONCLUIDA em {time.ctime(time.time())}")
            else:
                log_terminal_event(f"Falha ao ATUALIZAR backup para {client_id} como CONCLUIDA: {backup_response.message}")
    except Exception as e:
        log_terminal_event(f"Erro RPC ao ATUALIZAR backup para {client_id} como CONCLUIDA: {e}")

    if callback_success:
        log_terminal_event(f"Notificação de CONCLUSÃO (via callback) enviada ao cliente {client_id} para veículo {assigned_vehicle_name} da classe {vehicle_class_available}.")
    else:
        log_terminal_event(f"FALHA na notificação de CONCLUSÃO (via callback) ao cliente {client_id} para veículo {assigned_vehicle_name}. Reserva concluída internamente.")

class TerminalServicer(terminal_pb2_grpc.TerminalServicer):
    def RentACar(self, request, context):
        client_id = request.ID_cliente
        client_ip = request.IP_cliente
        client_port = request.Porta_cliente
        requested_class = request.Classe_veiculo
        current_timestamp_obj = time.time()
        current_timestamp_str = time.ctime(current_timestamp_obj)
        
        log_terminal_event(f"Requisição recebida do cliente {client_id} ({client_ip}:{client_port}) para classe {requested_class} em {current_timestamp_str}")

        assigned_vehicle_name = None
        status_response = "PENDENTE" 

        with fleet_lock:
            if requested_class not in FLEET:
                FLEET[requested_class] = [] 
                log_terminal_event(f"Classe {requested_class} não encontrada na frota inicial, adicionada para gerenciamento.")

            for vehicle in FLEET[requested_class]:
                if vehicle["available"]:
                    vehicle["available"] = False
                    vehicle["rented_to_client_id"] = client_id 
                    assigned_vehicle_name = vehicle["name"]
                    status_response = "CONCLUIDO"
                    break
        
        try:
            with grpc.insecure_channel(BACKUP_SERVER_ADDRESS) as channel:
                backup_stub = backup_pb2_grpc.BackupServiceStub(channel)
                backup_req_msg_vehicle_name = assigned_vehicle_name if assigned_vehicle_name else ""
                
                log_terminal_event(f"Requisição enviada ao servidor de backup para cliente {client_id}, classe {requested_class}, veículo '{backup_req_msg_vehicle_name}', status {status_response} em {current_timestamp_str}")
                
                backup_req = backup_pb2.TransactionRequest(
                    terminal_id=TERMINAL_ID,
                    vehicle_class=requested_class,
                    vehicle_name=backup_req_msg_vehicle_name,
                    status=status_response
                )
                backup_resp = backup_stub.LogTransaction(backup_req)
                
                if not backup_resp.success:
                    log_terminal_event(f"Falha ao registrar no backup server: {backup_resp.message}. Revertendo operação local.")
                    if assigned_vehicle_name: 
                        with fleet_lock:
                            for vehicle in FLEET[requested_class]:
                                if vehicle["name"] == assigned_vehicle_name and vehicle["rented_to_client_id"] == client_id:
                                    vehicle["available"] = True
                                    vehicle["rented_to_client_id"] = None
                                    log_terminal_event(f"Rollback: Veículo {assigned_vehicle_name} tornado disponível novamente.")
                                    break
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details(f"Falha interna ao contatar servidor de backup: {backup_resp.message}")
                    log_terminal_event(f"Resposta recebida do servidor de backup (FALHA): {backup_resp.message} para cliente {client_id}, classe {requested_class}, veículo '{backup_req_msg_vehicle_name}', status {status_response} em {time.ctime(time.time())}")
                    return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_BACKUP")

                log_terminal_event(f"Resposta recebida do servidor de backup (SUCESSO) para cliente {client_id}, classe {requested_class}, veículo '{backup_req_msg_vehicle_name}', status {status_response} em {time.ctime(time.time())}")

        except grpc.RpcError as e:
            log_terminal_event(f"Erro RPC ao contatar Backup Server: {e.code()} - {e.details()}. A operação não pôde ser confirmada.")
            if assigned_vehicle_name: 
                 with fleet_lock:
                    for vehicle in FLEET[requested_class]:
                        if vehicle["name"] == assigned_vehicle_name and vehicle["rented_to_client_id"] == client_id:
                            vehicle["available"] = True
                            vehicle["rented_to_client_id"] = None
                            log_terminal_event(f"Rollback RPC: Veículo {assigned_vehicle_name} tornado disponível.")
                            break
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Falha de comunicação com o servidor de backup: {e.details()}")
            return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_BACKUP_RPC")

        if status_response == "PENDENTE":
            with waiting_list_lock:
                if requested_class not in waiting_list:
                    waiting_list[requested_class] = []
                waiting_list[requested_class].append({
                    "client_id": client_id, 
                    "client_ip": client_ip,
                    "client_port": client_port,
                    "original_request": request 
                })
            log_terminal_event(f"Cliente {client_id} adicionado à lista de espera para classe {requested_class}.")
            log_terminal_event(f"Resposta enviada ao cliente {client_id}: {status_response} {requested_class} em {time.ctime(time.time())}")
            return terminal_pb2.RentCarResponse(item_name=requested_class, status=status_response)
        else: 
            log_terminal_event(f"Veículo {assigned_vehicle_name} da classe {requested_class} alocado para {client_id}.")
            log_terminal_event(f"Resposta enviada ao cliente {client_id}: {status_response} {requested_class} {assigned_vehicle_name} em {time.ctime(time.time())}")
            return terminal_pb2.RentCarResponse(item_name=assigned_vehicle_name, status=status_response)

    def ReturnVehicle(self, request, context):
        client_id = request.ID_cliente
        vehicle_name_returned = request.nome_veiculo
        current_timestamp_str = time.ctime(time.time())

        log_terminal_event(f"Requisição de DEVOLUÇÃO recebida do cliente {client_id} para o veículo '{vehicle_name_returned}' em {current_timestamp_str}")

        vehicle_found_for_client = False
        returned_vehicle_class = None 

        with fleet_lock:
            for car_class_key, vehicles_in_class_list in FLEET.items():
                for vehicle_obj in vehicles_in_class_list:
                    if vehicle_obj["name"] == vehicle_name_returned:
                        if not vehicle_obj["available"] and vehicle_obj["rented_to_client_id"] == client_id:
                            vehicle_obj["available"] = True
                            vehicle_obj["rented_to_client_id"] = None
                            vehicle_found_for_client = True
                            returned_vehicle_class = car_class_key 
                            log_terminal_event(f"Veículo '{vehicle_name_returned}' da classe '{returned_vehicle_class}' devolvido por {client_id} e agora está disponível.")
                            break
                        elif vehicle_obj["available"]:
                            log_terminal_event(f"Tentativa de devolução do veículo '{vehicle_name_returned}' por {client_id}, mas o veículo já constava como disponível.")
                            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                            context.set_details(f"Veículo '{vehicle_name_returned}' já está disponível.")
                            return terminal_pb2.ReturnVehicleResponse(status="ERRO_VEICULO_JA_DISPONIVEL", message=f"Veículo '{vehicle_name_returned}' já está disponível.")
                        else: 
                            log_terminal_event(f"Tentativa de devolução do veículo '{vehicle_name_returned}' por {client_id}, mas está alugado para '{vehicle_obj['rented_to_client_id']}'.")
                            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                            context.set_details(f"Veículo '{vehicle_name_returned}' não está alugado para o cliente {client_id}.")
                            return terminal_pb2.ReturnVehicleResponse(status="ERRO_CLIENTE_INVALIDO", message="Veículo não alugado para este cliente.")
                if vehicle_found_for_client:
                    break
        
        if not vehicle_found_for_client:
            log_terminal_event(f"Tentativa de devolução do veículo '{vehicle_name_returned}' por {client_id}, mas o veículo não foi encontrado na frota como alugado por este cliente.")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Veículo '{vehicle_name_returned}' não encontrado como alugado por {client_id}.")
            return terminal_pb2.ReturnVehicleResponse(status="ERRO_VEICULO_NAO_ENCONTRADO", message="Veículo não encontrado ou não corresponde à locação atual deste cliente.")

        backup_status_for_return = "DEVOLVIDO" 
        try:
            with grpc.insecure_channel(BACKUP_SERVER_ADDRESS) as channel:
                backup_stub = backup_pb2_grpc.BackupServiceStub(channel)
                # Para o log de backup, a especificação é "classe [classe solicitada] [nome do veículo] [status]"
                # O `returned_vehicle_class` é importante aqui.
                log_terminal_event(f"Requisição enviada ao servidor de backup para cliente {client_id}, classe {returned_vehicle_class}, veículo '{vehicle_name_returned}', status {backup_status_for_return} em {current_timestamp_str}")
                backup_req = backup_pb2.TransactionRequest(
                    terminal_id=TERMINAL_ID,
                    vehicle_class=returned_vehicle_class, 
                    vehicle_name=vehicle_name_returned,
                    status=backup_status_for_return 
                )
                backup_resp = backup_stub.LogTransaction(backup_req)
                if backup_resp.success:
                    log_terminal_event(f"Resposta recebida do servidor de backup (SUCESSO) para devolução do veículo '{vehicle_name_returned}' pelo cliente {client_id} em {time.ctime(time.time())}")
                else:
                    log_terminal_event(f"Falha ao registrar DEVOLUÇÃO no backup server para veículo '{vehicle_name_returned}': {backup_resp.message}.")
        except grpc.RpcError as e:
            log_terminal_event(f"Erro RPC ao contatar Backup Server para registrar DEVOLUÇÃO do veículo '{vehicle_name_returned}': {e}.")
        
        if returned_vehicle_class:
            log_terminal_event(f"Veículo da classe '{returned_vehicle_class}' devolvido. Verificando lista de espera...")
            threading.Thread(target=process_waiting_list_for_class, args=(returned_vehicle_class,), daemon=True).start()

        log_terminal_event(f"Resposta enviada ao cliente {client_id}: DEVOLVIDO_SUCESSO {returned_vehicle_class} {vehicle_name_returned} em {time.ctime(time.time())}")
        return terminal_pb2.ReturnVehicleResponse(status="DEVOLVIDO_SUCESSO", message=f"Veículo '{vehicle_name_returned}' devolvido com sucesso.")

def serve():
    log_terminal_event("Iniciando servidor...")
    hb_thread = threading.Thread(
        target=send_heartbeats_to_master,
        args=(TERMINAL_ID, HEARTBEAT_SERVER_ADDRESS, HEARTBEAT_SEND_INTERVAL),
        daemon=True
    )
    hb_thread.start()
    log_terminal_event("Thread de Heartbeat iniciada.")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    terminal_pb2_grpc.add_TerminalServicer_to_server(TerminalServicer(), server)
    
    server.add_insecure_port(f'[::]:{TERMINAL_PORT}')
    log_terminal_event(f"Servidor do Terminal {TERMINAL_ID} iniciado na porta {TERMINAL_PORT}.")
    print(f"Servidor do Terminal {TERMINAL_ID} rodando na porta {TERMINAL_PORT}...")
    
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        log_terminal_event("Servidor do Terminal encerrado.")
        print(f"Servidor do Terminal {TERMINAL_ID} encerrado.")
        server.stop(0)

if __name__ == '__main__':
    with open(TERMINAL_LOG_FILE, "w") as f: 
        f.write(f"{time.ctime(time.time())}: Log do Terminal {TERMINAL_ID} iniciado.\n")
    serve()