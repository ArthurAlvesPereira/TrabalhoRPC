# info_server.py

import grpc
import time
from concurrent import futures
import threading
import random

# Módulos gerados (agora de guiche_info.proto)
import guiche_info_pb2
import guiche_info_pb2_grpc

HEARTBEAT_LOG_FILE = "heartbeat.txt"

# Mapeamento predefinido de IDs de terminal para seus endereços.
TERMINAL_ADDRESSES = {
    "terminal_1": "localhost:50151",
    "terminal_2": "localhost:50152",
    "terminal_3": "localhost:50153",
}

active_terminals_cache = [] # Cache de terminais ativos [{ "id": "terminal_1", "address": "localhost:50151"}]
cache_lock = threading.Lock()
CACHE_UPDATE_INTERVAL = 10 # Segundos para reler o heartbeat.txt

def update_active_terminals_cache():
    global active_terminals_cache
    current_statuses = {}
    try:
        with open(HEARTBEAT_LOG_FILE, "r") as f:
            for line in f:
                parts = line.strip().split(" ")
                if len(parts) > 3 and parts[0].startswith("terminal_") and parts[1] == "está": # Verifica se é um terminal
                    service_id = parts[0]
                    status = parts[2].replace(",", "")
                    if service_id in TERMINAL_ADDRESSES:
                        current_statuses[service_id] = status
    except FileNotFoundError:
        print(f"INFO_SERVER: Arquivo {HEARTBEAT_LOG_FILE} não encontrado.")
        return
    except Exception as e:
        print(f"INFO_SERVER: Erro ao ler {HEARTBEAT_LOG_FILE}: {e}")
        return

    new_active_list = []
    for service_id, status in current_statuses.items():
        if status == "ativo": # Somente considera terminais ativos
            new_active_list.append({
                "id": service_id,
                "address": TERMINAL_ADDRESSES[service_id]
            })
    
    with cache_lock:
        active_terminals_cache = new_active_list
    # print(f"INFO_SERVER: Cache de terminais ativos atualizado: {active_terminals_cache}")


def periodic_cache_updater():
    while True:
        update_active_terminals_cache()
        time.sleep(CACHE_UPDATE_INTERVAL)

# A classe agora herda de InformationServicer
class InformationServicer(guiche_info_pb2_grpc.InformationServicer):
    # O método agora é GetTerminalOnLine e espera guiche_info_pb2.Empty
    def GetTerminalOnLine(self, request, context):
        # request é do tipo guiche_info_pb2.Empty, não tem campos para usar.
        
        with cache_lock:
            if not active_terminals_cache:
                print("INFO_SERVER: Nenhum terminal ativo encontrado no cache.")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Nenhum terminal de atendimento ativo encontrado no momento.")
                # Retorna uma resposta vazia, mas com o código de erro e detalhes no contexto
                return guiche_info_pb2.TerminalAddressResponse()

            chosen_terminal_info = random.choice(active_terminals_cache)
            terminal_address = chosen_terminal_info["address"] # O cliente espera o endereço no campo 'message'
            
            print(f"INFO_SERVER: Cliente solicitou terminal. Enviando endereço: {terminal_address}")
            # A resposta agora é TerminalAddressResponse e o endereço vai no campo 'message'
            return guiche_info_pb2.TerminalAddressResponse(message=terminal_address)

def serve():
    updater_thread = threading.Thread(target=periodic_cache_updater, daemon=True)
    updater_thread.start()
    
    # <<< ADICIONE ESTA LINHA >>>
    print("INFO_SERVER: Realizando primeira atualização do cache de terminais ativos...")
    update_active_terminals_cache() # Para popular o cache uma vez no início
    # <<< FIM DA LINHA ADICIONADA >>>

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    # Adiciona o InformationServicer ao servidor
    guiche_info_pb2_grpc.add_InformationServicer_to_server(InformationServicer(), server)
    
    # Porta atualizada para 50051, conforme o cliente do professor
    info_server_port = "50051" 
    server.add_insecure_port(f'[::]:{info_server_port}')
    print(f"Servidor de Informações (Guichê) iniciado na porta {info_server_port}.")
    
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Servidor de Informações encerrado.")
        server.stop(0)

if __name__ == '__main__':
    # Para garantir que o cache seja populado uma vez no início, se desejado, antes do loop
    # update_active_terminals_cache() 
    serve()