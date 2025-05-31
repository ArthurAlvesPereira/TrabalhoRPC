# terminal_1.py

import grpc
import time
from concurrent import futures
import threading
import random # Para simular tempo de uso do veículo

# Módulos gerados
import terminal_pb2
import terminal_pb2_grpc
import heartbeat_pb2 # Cliente do Heartbeat
import heartbeat_pb2_grpc # Cliente do Heartbeat
import backup_pb2 # Cliente do Backup
import backup_pb2_grpc # Cliente do Backup

# --- Configurações do Terminal ---
TERMINAL_ID = "terminal_1"
TERMINAL_PORT = "50151" # Porta específica para este terminal
HEARTBEAT_SERVER_ADDRESS = 'localhost:50051'
BACKUP_SERVER_ADDRESS = 'localhost:50051' # Porta do backup_server.py
HEARTBEAT_SEND_INTERVAL = 4 # Segundos
TERMINAL_LOG_FILE = f"terminal_{TERMINAL_ID}.txt"

# Classes de veículos e frota inicial para Terminal 1 [cite: 15]
# Estrutura: {'classe': [{'name': 'Nome Veiculo', 'available': True, 'client_id': None}, ...]}
FLEET = {
    "Executivos": [
        {"name": "BMW Série 5", "available": True, "client_id": None},
        {"name": "Toyota Corolla Altis Híbrido", "available": True, "client_id": None},
    ],
    "Minivans": [
        {"name": "Chevrolet Spin", "available": True, "client_id": None},
        {"name": "Fiat Doblo", "available": True, "client_id": None},
        {"name": "Nissan Livina", "available": True, "client_id": None},
        {"name": "Citroën C4 Picasso", "available": True, "client_id": None},
        {"name": "Chevrolet Zafira", "available": True, "client_id": None},
    ]
}
# TODO: Adicionar outras classes mesmo que vazias, pois o terminal pode receber pedidos [cite: 16]
# FLEET["Econômicos"] = []
# FLEET["Intermediários"] = []
# FLEET["SUV"] = []


fleet_lock = threading.Lock() # Para acesso seguro à FLEET
waiting_list = {} # {'classe_veiculo': [{'client_id': id, 'request_data': request}, ...]}
waiting_list_lock = threading.Lock()

# --- Funções de Log do Terminal ---
# Formatos de log do terminal [cite: 9, 10]
def log_terminal_event(message):
    with open(TERMINAL_LOG_FILE, "a") as f:
        f.write(f"{time.ctime(time.time())}: {message}\n")
    print(f"LOG {TERMINAL_ID}: {message}")


# --- Cliente de Heartbeat (similar ao do backup_server.py) ---
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
        time.sleep(interval) # Espera antes de tentar recriar o canal

# --- [NOVO] Função para tentar processar a lista de espera para uma classe ---
def process_waiting_list_for_class(vehicle_class_available):
    with waiting_list_lock:
        if vehicle_class_available in waiting_list and waiting_list[vehicle_class_available]:
            pending_client_info = waiting_list[vehicle_class_available].pop(0) # Pega o primeiro da fila (FIFO)
            # Se a lista ficar vazia, remove a chave
            if not waiting_list[vehicle_class_available]:
                del waiting_list[vehicle_class_available]
        else:
            return # Ninguém na lista de espera para esta classe

    client_id = pending_client_info["client_id"]
    client_ip = pending_client_info["client_ip"]
    client_port = pending_client_info["client_port"]
    # original_request_obj = pending_client_info["original_request"] # Pode ser usado se precisar de mais dados

    log_terminal_event(f"Tentando atender cliente {client_id} da lista de espera para classe {vehicle_class_available}.")

    assigned_vehicle_name = None
    with fleet_lock: # Tenta alocar o veículo novamente
        for vehicle in FLEET.get(vehicle_class_available, []):
            if vehicle["available"]:
                vehicle["available"] = False
                vehicle["rented_to_client_id"] = client_id
                assigned_vehicle_name = vehicle["name"]
                break
    
    if not assigned_vehicle_name:
        log_terminal_event(f"ERRO INTERNO: Veículo da classe {vehicle_class_available} deveria estar disponível para {client_id} da lista de espera, mas não foi encontrado. Repondo cliente na lista.")
        # Recoloca o cliente na lista de espera (no início)
        with waiting_list_lock:
            if vehicle_class_available not in waiting_list:
                waiting_list[vehicle_class_available] = []
            waiting_list[vehicle_class_available].insert(0, pending_client_info)
        return

    # 1. Notificar o cliente via callback
    callback_success = False
    try:
        client_callback_address = f"{client_ip}:{client_port}"
        log_terminal_event(f"Tentando callback para {client_id} em {client_callback_address} para veículo {assigned_vehicle_name}...")
        with grpc.insecure_channel(client_callback_address) as channel:
            callback_stub = terminal_pb2_grpc.CallbackServiceStub(channel)
            callback_message_content = f"Seu veículo '{assigned_vehicle_name}' da classe '{vehicle_class_available}' está pronto!"
            cb_message = terminal_pb2.CallbackMessage(message_content=callback_message_content)
            cb_response = callback_stub.ReceiveCallback(cb_message, timeout=5) # Adiciona timeout
            if cb_response and cb_response.status == "Callback Recebido OK":
                log_terminal_event(f"Callback para {client_id} bem-sucedido: {cb_response.status}")
                callback_success = True
            else:
                log_terminal_event(f"Callback para {client_id} retornou status inesperado: {cb_response.status if cb_response else 'Sem resposta'}")
    except grpc.RpcError as e:
        log_terminal_event(f"Falha no callback para {client_id} ({client_callback_address}): {e.code()} - {e.details()}")
    except Exception as e:
        log_terminal_event(f"Exceção durante callback para {client_id}: {e}")

    # Mesmo se o callback falhar, a especificação parece implicar que a locação é concluída
    # "Assim que existir um veículo disponível... o cliente deverá ser atendido (enviar msg ao cliente de CONCLUIDO e para servidor de backup como CONCLUIDO)" [cite: 8]
    # A falha no callback é um problema de notificação, mas a reserva pode prosseguir internamente.

    # 2. Atualizar o Servidor de Backup para CONCLUIDO
    log_terminal_event(f"Veículo {assigned_vehicle_name} alocado para {client_id} da lista de espera. Atualizando backup.")
    try:
        with grpc.insecure_channel(BACKUP_SERVER_ADDRESS) as channel:
            backup_stub = backup_pb2_grpc.BackupServiceStub(channel)
            backup_request = backup_pb2.TransactionRequest(
                terminal_id=TERMINAL_ID,
                vehicle_class=vehicle_class_available,
                vehicle_name=assigned_vehicle_name,
                status="CONCLUIDA" # Agora é CONCLUIDA
            )
            backup_response = backup_stub.LogTransaction(backup_request)
            if backup_response.success:
                log_terminal_event(f"Backup atualizado para {client_id}, classe {vehicle_class_available}, veículo {assigned_vehicle_name} como CONCLUIDA.")
            else:
                log_terminal_event(f"Falha ao ATUALIZAR backup para {client_id} como CONCLUIDA: {backup_response.message}")
                # TODO: O que fazer se o backup falhar aqui? A alocação já ocorreu.
    except Exception as e:
        log_terminal_event(f"Erro RPC ao ATUALIZAR backup para {client_id} como CONCLUIDA: {e}")

    # Log da transação para o terminal
    # "Requisição enviada ao servidor de backup [identificação do cliente] para classe [classe solicitada] [nome do veículo] CONCLUIDA em [timestamp]" [cite: 10]
    # "Resposta recebida do servidor de backup [identificação do cliente][classe][nome do veículo] CONCLUIDA em [timestamp]" [cite: 10]
    # (Já logado acima)

    # "Resposta enviada ao cliente [identificação do cliente]: [status] [classe][nome do veículo] em [timestamp]" [cite: 10]
    # Esta mensagem é o callback, mas o log do terminal registra a conclusão.
    if callback_success:
        log_terminal_event(f"Notificação de CONCLUSÃO (via callback) enviada ao cliente {client_id} para veículo {assigned_vehicle_name} da classe {vehicle_class_available}.")
    else:
        log_terminal_event(f"FALHA na notificação de CONCLUSÃO (via callback) ao cliente {client_id} para veículo {assigned_vehicle_name}. Reserva concluída internamente.")



# --- Servicer gRPC do Terminal ---
class TerminalServicer(terminal_pb2_grpc.TerminalServicer): # MODIFICADO para TerminalServicer
    # MODIFICADO para RentACar e novos nomes de campos/mensagens
    def RentACar(self, request, context):
        # Extrai dados da requisição com os novos nomes de campos
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
            # Garante que a classe exista no dicionário FLEET para evitar KeyErrors
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
        
        # Comunicação com o Servidor de Backup
        try:
            with grpc.insecure_channel(BACKUP_SERVER_ADDRESS) as channel:
                backup_stub = backup_pb2_grpc.BackupServiceStub(channel)
                backup_req = backup_pb2.TransactionRequest(
                    terminal_id=TERMINAL_ID,
                    vehicle_class=requested_class,
                    vehicle_name=assigned_vehicle_name if assigned_vehicle_name else "",
                    status=status_response
                )
                # Log da requisição enviada ao backup (formato do doc)
                log_terminal_event(f"Requisição enviada ao servidor de backup para cliente {client_id}, classe {requested_class}, veículo '{assigned_vehicle_name if assigned_vehicle_name else ''}', status {status_response} em {current_timestamp_str}")
                
                backup_resp = backup_stub.LogTransaction(backup_req)
                
                if not backup_resp.success:
                    log_terminal_event(f"Falha ao registrar no backup server: {backup_resp.message}. Revertendo operação local.")
                    if assigned_vehicle_name: # Se um carro foi alocado, desfaz
                        with fleet_lock:
                            for vehicle in FLEET[requested_class]:
                                if vehicle["name"] == assigned_vehicle_name and vehicle["rented_to_client_id"] == client_id:
                                    vehicle["available"] = True
                                    vehicle["rented_to_client_id"] = None
                                    log_terminal_event(f"Rollback: Veículo {assigned_vehicle_name} tornado disponível novamente.")
                                    break
                    context.set_code(grpc.StatusCode.INTERNAL)
                    context.set_details(f"Falha interna ao contatar servidor de backup: {backup_resp.message}")
                    log_terminal_event(f"Resposta recebida do servidor de backup (FALHA): {backup_resp.message} em {time.ctime(time.time())}")
                    # Não envia PENDENTE ou CONCLUIDO ao cliente se o backup falhou criticamente
                    return terminal_pb2.RentCarResponse(item_name=requested_class, status="ERRO_BACKUP")

                log_terminal_event(f"Resposta recebida do servidor de backup (SUCESSO) para cliente {client_id}, status {status_response} em {time.ctime(time.time())}")

        except grpc.RpcError as e:
            log_terminal_event(f"Erro RPC ao contatar Backup Server: {e.code()} - {e.details()}. A operação não pôde ser confirmada.")
            if assigned_vehicle_name: # Rollback se possível
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

        # Resposta ao Cliente
        if status_response == "PENDENTE":
            with waiting_list_lock:
                if requested_class not in waiting_list:
                    waiting_list[requested_class] = []
                # [NOVO] Armazena IP e Porta do cliente para callback
                waiting_list[requested_class].append({
                    "client_id": client_id, 
                    "client_ip": client_ip,
                    "client_port": client_port,
                    "original_request": request # Pode ser útil ter o objeto request original
                })
            log_terminal_event(f"Cliente {client_id} adicionado à lista de espera para classe {requested_class}.")
            # Log da resposta enviada ao cliente
            log_terminal_event(f"Resposta enviada ao cliente {client_id}: {status_response} {requested_class} em {time.ctime(time.time())}")
            return terminal_pb2.RentCarResponse(item_name=requested_class, status=status_response)
        else: # CONCLUIDO
            log_terminal_event(f"Veículo {assigned_vehicle_name} da classe {requested_class} alocado para {client_id}.")
             # Log da resposta enviada ao cliente
            log_terminal_event(f"Resposta enviada ao cliente {client_id}: {status_response} {requested_class} {assigned_vehicle_name} em {time.ctime(time.time())}")
            return terminal_pb2.RentCarResponse(item_name=assigned_vehicle_name, status=status_response)

    # TODO: Implementar ReturnVehicle
    # Quando ReturnVehicle for implementado, ele deverá chamar process_waiting_list_for_class(classe_do_veiculo_devolvido)


# --- Função Principal do Servidor ---
def serve():
    log_terminal_event("Iniciando servidor...")
    # Iniciar thread de heartbeat para este terminal
    hb_thread = threading.Thread(
        target=send_heartbeats_to_master,
        args=(TERMINAL_ID, HEARTBEAT_SERVER_ADDRESS, HEARTBEAT_SEND_INTERVAL),
        daemon=True
    )
    hb_thread.start()
    log_terminal_event("Thread de Heartbeat iniciada.")

    # Configurar e iniciar o servidor gRPC para o serviço do Terminal
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
    # Limpar log antigo ao iniciar (opcional)
    with open(TERMINAL_LOG_FILE, "w") as f:
        f.write(f"{time.ctime(time.time())}: Log do Terminal {TERMINAL_ID} iniciado.\n")
    serve()
    