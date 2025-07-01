# terminal_3.py

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

# Configs para terminal 3
TERMINAL_ID = "terminal_3"
TERMINAL_PORT = "50153"
MY_PRIMARY_MANAGED_CLASSES = ["Economicos"]
FLEET = {
    "Economicos": [
        {"name": "Chevrolet Onix", "available": True, "rented_to_client_id": None},
        {"name": "Renault Kwid", "available": True, "rented_to_client_id": None},
        {"name": "Peugeot 208", "available": True, "rented_to_client_id": None},
    ]
}


HEARTBEAT_SERVER_ADDRESS = 'localhost:50050'
BACKUP_SERVER_ADDRESS = 'localhost:50055'
HEARTBEAT_SEND_INTERVAL = 5
TERMINAL_LOG_FILE = f"terminal_{TERMINAL_ID}.txt"

CLASS_PRIMARY_TERMINAL_MAP = {
    "Economicos": "localhost:50153",
    "Intermediarios": "localhost:50152",
    "SUV": "localhost:50152",
    "Executivos": "localhost:50151",
    "Minivan": "localhost:50151",
}
ALL_POSSIBLE_CLASSES = ["Economicos", "Intermediarios", "SUV", "Executivos", "Minivan"]
for vc_class in ALL_POSSIBLE_CLASSES:
    if vc_class not in FLEET:
        FLEET[vc_class] = []

fleet_lock = threading.Lock()
waiting_list = {}
waiting_list_lock = threading.Lock()

def log_terminal_event(message):
    log_line = f"{time.ctime(time.time())}: {TERMINAL_ID}: {message}"
    print(f"LOG {TERMINAL_ID}: {message}")
    with open(TERMINAL_LOG_FILE, "a", encoding='utf-8') as f:
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

def _register_with_backup(client_id, requested_class, vehicle_name, status, timestamp_str):
    try:
        with grpc.insecure_channel(BACKUP_SERVER_ADDRESS) as channel:
            backup_stub = backup_pb2_grpc.BackupServiceStub(channel)
            actual_vehicle_name = vehicle_name if vehicle_name else ""
            log_terminal_event(f"Requisição enviada ao servidor de backup para cliente {client_id}, classe {requested_class}, veículo '{actual_vehicle_name}', status {status} em {timestamp_str}")
            backup_request = backup_pb2.TransactionRequest(
                terminal_id=TERMINAL_ID, vehicle_class=requested_class,
                vehicle_name=actual_vehicle_name, status=status
            )
            backup_response = backup_stub.LogTransaction(backup_request, timeout=5)
            if backup_response.success:
                log_terminal_event(f"Resposta recebida do servidor de backup (SUCESSO) para cliente {client_id}, classe {requested_class}, veículo '{actual_vehicle_name}', status {status} em {time.ctime(time.time())}")
                return True
            else:
                log_terminal_event(f"Falha ao registrar no backup server para cliente {client_id} ({status}): {backup_response.message}")
                log_terminal_event(f"Resposta recebida do servidor de backup (FALHA) para cliente {client_id}, classe {requested_class}, veículo '{actual_vehicle_name}', status {status} em {time.ctime(time.time())}")
                return False
    except grpc.RpcError as e:
        log_terminal_event(f"Erro RPC ao contatar Backup Server para cliente {client_id} ({status}): {e.code()} - {e.details()}.")
        return False
    except Exception as e_gen:
        log_terminal_event(f"Exceção inesperada ao contatar Backup Server para cliente {client_id} ({status}): {e_gen}.")
        return False

def process_waiting_list_for_class(vehicle_class_available):
    log_terminal_event(f"Process_waiting_list INICIADA para classe '{vehicle_class_available}'")
    pending_client_info = None
    with waiting_list_lock:
        if vehicle_class_available in waiting_list and waiting_list[vehicle_class_available]:
            pending_client_info = waiting_list[vehicle_class_available].pop(0)
            log_terminal_event(f"Cliente retirado da lista de espera para '{vehicle_class_available}': {pending_client_info.get('client_id') if pending_client_info else 'N/A'}")
            if not waiting_list[vehicle_class_available]:
                del waiting_list[vehicle_class_available]
        else:
            log_terminal_event(f"Process_waiting_list: Lista de espera para '{vehicle_class_available}' está vazia ou não existe.")
            return

    if not pending_client_info:
        log_terminal_event(f"Process_waiting_list: Nenhum cliente encontrado na lista para '{vehicle_class_available}'.")
        return

    client_id = pending_client_info["client_id"]
    client_ip = pending_client_info["client_ip"]
    client_port = pending_client_info["client_port"]

    log_terminal_event(f"Tentando atender cliente {client_id} da lista de espera para classe {vehicle_class_available}.")
    log_terminal_event(f"Estado atual da frota para '{vehicle_class_available}' ANTES da alocação para lista de espera: {FLEET.get(vehicle_class_available)}")

    assigned_vehicle_name = None
    with fleet_lock:
        if vehicle_class_available not in MY_PRIMARY_MANAGED_CLASSES:
             log_terminal_event(f"AVISO INTERNO: process_waiting_list para {vehicle_class_available} que não é primária de {TERMINAL_ID}. Cliente {client_id} não será processado.")
             with waiting_list_lock:
                if vehicle_class_available not in waiting_list: waiting_list[vehicle_class_available] = []
                waiting_list[vehicle_class_available].insert(0, pending_client_info)
             return

        for vehicle in FLEET.get(vehicle_class_available, []):
            if vehicle["available"]:
                vehicle["available"] = False
                vehicle["rented_to_client_id"] = client_id
                assigned_vehicle_name = vehicle["name"]
                break
    
    if not assigned_vehicle_name:
        log_terminal_event(f"NÃO FOI POSSÍVEL alocar veículo da classe {vehicle_class_available} para {client_id} da lista de espera. Repondo cliente na lista.")
        with waiting_list_lock:
            if vehicle_class_available not in waiting_list:
                waiting_list[vehicle_class_available] = []
            waiting_list[vehicle_class_available].insert(0, pending_client_info)
        return

    log_terminal_event(f"Veículo local {assigned_vehicle_name} alocado para {client_id} da lista de espera. Registrando no backup.")
    backup_registration_ok = _register_with_backup(
        client_id, vehicle_class_available, assigned_vehicle_name, "CONCLUIDA", time.ctime(time.time())
    )

    if not backup_registration_ok:
        log_terminal_event(f"Falha ao registrar no backup a alocação para {client_id} da lista de espera. Revertendo.")
        with fleet_lock:
            for vehicle in FLEET.get(vehicle_class_available, []):
                if vehicle["name"] == assigned_vehicle_name and vehicle["rented_to_client_id"] == client_id:
                    vehicle["available"] = True
                    vehicle["rented_to_client_id"] = None
                    break
        with waiting_list_lock:
            if vehicle_class_available not in waiting_list: waiting_list[vehicle_class_available] = []
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
                log_terminal_event(f"Callback para {client_id} retornou status inesperado: {cb_response.status if cb_response else 'Sem resposta ou timeout'}")
    except grpc.RpcError as e:
        log_terminal_event(f"Falha no callback RPC para {client_id} ({client_callback_address}): {e.code()} - {e.details()}")
    except Exception as e:
        log_terminal_event(f"Exceção durante callback para {client_id}: {e}")

    if callback_success:
        log_terminal_event(f"Notificação de CONCLUSÃO (via callback) enviada ao cliente {client_id} para veículo {assigned_vehicle_name} da classe {vehicle_class_available}.")
    else:
        log_terminal_event(f"FALHA na notificação de CONCLUSÃO (via callback) ao cliente {client_id}. A reserva do veículo {assigned_vehicle_name} está concluída internamente, mas o cliente não foi notificado com sucesso.")
    log_terminal_event(f"Process_waiting_list CONCLUÍDA para cliente {client_id}, veículo {assigned_vehicle_name}.")

class TerminalServicer(terminal_pb2_grpc.TerminalServicer):
    def RentACar(self, request, context):
        client_id = request.ID_cliente
        client_ip = request.IP_cliente
        client_port = request.Porta_cliente
        
        requested_class_raw = request.Classe_veiculo
        requested_class = requested_class_raw.strip()
        
        current_timestamp_obj = time.time()
        current_timestamp_str = time.ctime(current_timestamp_obj)
        
        log_terminal_event(f"Requisição recebida do cliente {client_id} ({client_ip}:{client_port}) para classe '{requested_class}' (raw: '{requested_class_raw}') em {current_timestamp_str}")

        is_primary_handler_for_class = requested_class in MY_PRIMARY_MANAGED_CLASSES

        if is_primary_handler_for_class:
            log_terminal_event(f"Terminal {TERMINAL_ID} é o handler primário para '{requested_class}'. Verificando frota local.")
            assigned_vehicle_name = None
            with fleet_lock:
                for vehicle in FLEET.get(requested_class, []):
                    if vehicle["available"]:
                        vehicle["available"] = False
                        vehicle["rented_to_client_id"] = client_id
                        assigned_vehicle_name = vehicle["name"]
                        break
            if assigned_vehicle_name:
                log_terminal_event(f"Veículo local '{assigned_vehicle_name}' da classe '{requested_class}' alocado para {client_id}.")
                if _register_with_backup(client_id, requested_class, assigned_vehicle_name, "CONCLUIDO", current_timestamp_str):
                    log_terminal_event(f"Resposta enviada ao cliente {client_id}: CONCLUIDO {requested_class} {assigned_vehicle_name} em {time.ctime(time.time())}")
                    return terminal_pb2.RentCarResponse(item_name=assigned_vehicle_name, status="CONCLUIDO")
                else: 
                    with fleet_lock: 
                        for vehicle in FLEET.get(requested_class, []):
                            if vehicle["name"] == assigned_vehicle_name and vehicle["rented_to_client_id"] == client_id:
                                vehicle["available"] = True
                                vehicle["rented_to_client_id"] = None
                                log_terminal_event(f"Rollback: Veículo {assigned_vehicle_name} tornado disponível novamente devido à falha no backup.")
                                break
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details("Falha ao registrar transação no servidor de backup.")
                    log_terminal_event(f"Resposta enviada ao cliente {client_id}: ERRO_BACKUP {requested_class} em {time.ctime(time.time())}")
                    return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_BACKUP")
            else: 
                log_terminal_event(f"Nenhum veículo local da classe '{requested_class}' disponível para {client_id}. Colocando na lista de espera.")
                if _register_with_backup(client_id, requested_class, None, "PENDENTE", current_timestamp_str):
                    with waiting_list_lock:
                        if requested_class not in waiting_list:
                            waiting_list[requested_class] = []
                        waiting_list[requested_class].append({
                            "client_id": client_id, "client_ip": client_ip,
                            "client_port": client_port, "original_request_details": request
                        })
                    log_terminal_event(f"Cliente {client_id} adicionado à lista de espera local para '{requested_class}'.")
                    log_terminal_event(f"Resposta enviada ao cliente {client_id}: PENDENTE {requested_class} em {time.ctime(time.time())}")
                    return terminal_pb2.RentCarResponse(item_name=requested_class, status="PENDENTE")
                else: 
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details("Falha ao registrar transação PENDENTE no servidor de backup.")
                    log_terminal_event(f"Resposta enviada ao cliente {client_id}: ERRO_BACKUP {requested_class} em {time.ctime(time.time())}")
                    return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_BACKUP")
        else: 
            target_terminal_address = CLASS_PRIMARY_TERMINAL_MAP.get(requested_class)
            if not target_terminal_address:
                log_terminal_event(f"ERRO DE CONFIGURAÇÃO: Classe '{requested_class}' solicitada por {client_id}, não é primária deste terminal E não há mapeamento para encaminhamento no CLASS_PRIMARY_TERMINAL_MAP.")
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"A classe de veículo '{requested_class}' não pode ser processada: configuração de encaminhamento ausente ou classe desconhecida.")
                log_terminal_event(f"Resposta enviada ao cliente {client_id}: ERRO_CLASSE_NAO_MAPEADA {requested_class} em {time.ctime(time.time())}")
                return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_CLASSE_NAO_MAPEADA")

            log_terminal_event(f"Terminal {TERMINAL_ID} não é primário para '{requested_class}'. Encaminhando para {target_terminal_address} para cliente {client_id}.")
            try:
                with grpc.insecure_channel(target_terminal_address) as channel:
                    stub = terminal_pb2_grpc.TerminalStub(channel)
                    forward_request = terminal_pb2.RentCarRequest(
                        ID_cliente=client_id, IP_cliente=client_ip,
                        Porta_cliente=client_port, Classe_veiculo=requested_class
                    )
                    log_terminal_event(f"Enviando requisição de encaminhamento para {target_terminal_address} para classe '{requested_class}' do cliente {client_id} em {current_timestamp_str}")
                    forward_response = stub.RentACar(forward_request, timeout=10)
                    log_terminal_event(f"Resposta de encaminhamento recebida de {target_terminal_address} para cliente {client_id}: status '{forward_response.status}', item '{forward_response.item_name}' em {time.ctime(time.time())}")
                    log_terminal_event(f"Resposta enviada ao cliente {client_id}: {forward_response.status} {forward_response.item_name} em {time.ctime(time.time())}")
                    return terminal_pb2.RentCarResponse(item_name=forward_response.item_name, status=forward_response.status)
            except grpc.RpcError as e:
                log_terminal_event(f"Erro RPC ao encaminhar para {target_terminal_address} para classe '{requested_class}' (cliente {client_id}): {e.code()} - {e.details()}")
                context.set_code(grpc.StatusCode.UNAVAILABLE)
                context.set_details(f"Falha ao comunicar com o terminal responsável pela classe '{requested_class}'. Tente novamente mais tarde.")
                log_terminal_event(f"Resposta enviada ao cliente {client_id}: ERRO_ENCAMINHAMENTO {requested_class} em {time.ctime(time.time())}")
                return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_ENCAMINHAMENTO")
            except Exception as e_gen:
                log_terminal_event(f"Exceção inesperada ao encaminhar para {target_terminal_address} (cliente {client_id}): {e_gen}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("Ocorreu um erro interno inesperado ao processar sua solicitação.")
                log_terminal_event(f"Resposta enviada ao cliente {client_id}: ERRO_INTERNO_INESPERADO {requested_class} em {time.ctime(time.time())}")
                return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_INTERNO_INESPERADO")

    def ReturnVehicle(self, request, context):
        client_id = request.ID_cliente
        vehicle_name_returned = request.nome_veiculo.strip() if request.nome_veiculo else ""
        current_timestamp_obj = time.time()
        current_timestamp_str = time.ctime(current_timestamp_obj)

        log_terminal_event(f"Requisição de DEVOLUÇÃO recebida do cliente {client_id} para o veículo '{vehicle_name_returned}' em {current_timestamp_str}")

        if not vehicle_name_returned:
            log_terminal_event(f"Tentativa de devolução sem nome de veículo por {client_id}.")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Nome do veículo para devolução não fornecido.")
            return terminal_pb2.ReturnVehicleResponse(status="ERRO_NOME_VEICULO_AUSENTE", message="Nome do veículo para devolução não fornecido.")

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
                            log_terminal_event(f"Tentativa de devolução do veículo '{vehicle_name_returned}' por {client_id}, mas o veículo já consta como disponível neste terminal.")
                            context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                            context.set_details(f"Veículo '{vehicle_name_returned}' já está disponível.")
                            return terminal_pb2.ReturnVehicleResponse(status="ERRO_VEICULO_JA_DISPONIVEL", message=f"Veículo '{vehicle_name_returned}' já está disponível.")
                        else: 
                            log_terminal_event(f"Tentativa de devolução do veículo '{vehicle_name_returned}' por {client_id}, mas está alugado para '{vehicle_obj['rented_to_client_id']}' neste terminal.")
                            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                            context.set_details(f"Veículo '{vehicle_name_returned}' não está alugado para o cliente {client_id} neste terminal.")
                            return terminal_pb2.ReturnVehicleResponse(status="ERRO_CLIENTE_INVALIDO", message="Veículo não alugado para este cliente neste terminal.")
                if vehicle_found_for_client:
                    break
        
        if not vehicle_found_for_client:
            log_terminal_event(f"Tentativa de devolução do veículo '{vehicle_name_returned}' por {client_id}, mas o veículo não foi encontrado na frota deste terminal como alugado por este cliente.")
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Veículo '{vehicle_name_returned}' não encontrado como alugado por {client_id} neste terminal.")
            return terminal_pb2.ReturnVehicleResponse(status="ERRO_VEICULO_NAO_ENCONTRADO_OU_INVALIDO", message="Veículo não encontrado ou não corresponde à locação atual deste cliente neste terminal.")

        backup_status_for_return = "DEVOLVIDO"
        if not _register_with_backup(client_id, returned_vehicle_class, vehicle_name_returned, backup_status_for_return, current_timestamp_str):
            log_terminal_event(f"ALERTA: Devolução local do veículo '{vehicle_name_returned}' por {client_id} bem-sucedida, MAS FALHOU AO REGISTRAR NO BACKUP.")
        
        if returned_vehicle_class and returned_vehicle_class in MY_PRIMARY_MANAGED_CLASSES:
            log_terminal_event(f"Veículo da classe '{returned_vehicle_class}' devolvido. Verificando lista de espera local...")
            threading.Thread(target=process_waiting_list_for_class, args=(returned_vehicle_class,), daemon=True).start()

        log_terminal_event(f"Resposta enviada ao cliente {client_id}: DEVOLVIDO_SUCESSO para veículo '{vehicle_name_returned}' em {time.ctime(time.time())}")
        return terminal_pb2.ReturnVehicleResponse(status="DEVOLVIDO_SUCESSO", message=f"Veículo '{vehicle_name_returned}' devolvido com sucesso.")

def serve():
    with open(TERMINAL_LOG_FILE, "w", encoding='utf-8') as f:
        f.write(f"{time.ctime(time.time())}: Log do Terminal {TERMINAL_ID} iniciado.\n")
    
    log_terminal_event(f"Iniciando servidor do Terminal {TERMINAL_ID} na porta {TERMINAL_PORT}...")
    log_terminal_event(f"Este terminal gerencia primariamente as classes: {MY_PRIMARY_MANAGED_CLASSES}")

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
    log_terminal_event(f"Servidor do Terminal {TERMINAL_ID} escutando na porta {TERMINAL_PORT}.")
    print(f"Servidor do Terminal {TERMINAL_ID} rodando na porta {TERMINAL_PORT}...")
    
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        log_terminal_event("Servidor do Terminal encerrado via KeyboardInterrupt.")
        print(f"\nServidor do Terminal {TERMINAL_ID} encerrado.")
    except Exception as e:
        log_terminal_event(f"Servidor do Terminal {TERMINAL_ID} encerrado devido a uma exceção: {e}")
        print(f"\nServidor do Terminal {TERMINAL_ID} encerrado devido a uma exceção: {e}")
    finally:
        if 'server' in locals() and server : server.stop(0)

if __name__ == '__main__':
    serve()