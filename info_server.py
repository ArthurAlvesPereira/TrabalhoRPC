# info_server.py

import grpc
import time
from concurrent import futures
import threading
import random

import guiche_info_pb2
import guiche_info_pb2_grpc

HEARTBEAT_LOG_FILE = "heartbeat.txt"

TERMINAL_ADDRESSES = {
    "terminal_1": "localhost:50151",
    "terminal_2": "localhost:50152",
    "terminal_3": "localhost:50153",
}

active_terminals_cache = []
cache_lock = threading.Lock()
CACHE_UPDATE_INTERVAL = 10

def update_active_terminals_cache():
    global active_terminals_cache
    current_statuses = {}
    try:
        with open(HEARTBEAT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(" ")
                if len(parts) > 3 and parts[0].startswith("terminal_") and parts[1] == "está":
                    service_id = parts[0]
                    status = parts[2].replace(",", "")
                    if service_id in TERMINAL_ADDRESSES:
                        current_statuses[service_id] = status
    except FileNotFoundError:
        print(f"INFO_SERVER: Arquivo {HEARTBEAT_LOG_FILE} não encontrado ao tentar atualizar cache.")

        return
    except Exception as e:
        print(f"INFO_SERVER: Erro ao ler {HEARTBEAT_LOG_FILE}: {e}")
        return

    new_active_list = []
    for service_id, status in current_statuses.items():
        if status == "ativo":
            new_active_list.append({
                "id": service_id,
                "address": TERMINAL_ADDRESSES[service_id]
            })
    
    with cache_lock:
        active_terminals_cache = new_active_list
    # print(f"INFO_SERVER (Debug): Cache de terminais ativos atualizado: {active_terminals_cache}")

def periodic_cache_updater():
    while True:
        update_active_terminals_cache()
        time.sleep(CACHE_UPDATE_INTERVAL)

class InformationServicer(guiche_info_pb2_grpc.InformationServicer):
    def GetTerminalOnLine(self, request, context):
        with cache_lock:
            if not active_terminals_cache:
                print("INFO_SERVER: Nenhum terminal ativo encontrado no cache para atender solicitação.")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Nenhum terminal de atendimento ativo encontrado no momento.")
                return guiche_info_pb2.TerminalAddressResponse()

            chosen_terminal_info = random.choice(active_terminals_cache)
            terminal_address = chosen_terminal_info["address"]
            
            print(f"INFO_SERVER: Cliente solicitou terminal. Enviando endereço: {terminal_address}")
            return guiche_info_pb2.TerminalAddressResponse(message=terminal_address)

def serve():
    updater_thread = threading.Thread(target=periodic_cache_updater, daemon=True)
    updater_thread.start()
    
    print("INFO_SERVER: Realizando primeira atualização do cache de terminais ativos...")
    update_active_terminals_cache()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    guiche_info_pb2_grpc.add_InformationServicer_to_server(InformationServicer(), server)
    
    info_server_port = "50051" 
    server.add_insecure_port(f'[::]:{info_server_port}')
    print(f"Servidor de Informações (Guichê) iniciado na porta {info_server_port}.")
    
    server.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("Servidor de Informações encerrado.")
    except Exception as e:
        print(f"Servidor de Informações encerrado devido a uma exceção: {e}")
    finally:
        if 'server' in locals() and server:
            server.stop(0)

if __name__ == '__main__':
    # Cria ou limpa o arquivo de log do servidor de informações
    # with open("info_server.txt", "w", encoding="utf-8") as f:
    #     f.write(f"{time.ctime(time.time())}: Log do Servidor de Informações iniciado.\n")
    serve()
