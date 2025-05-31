# heartbeat_client_tester.py

import grpc
import time
import sys

# Importe os módulos gerados
import heartbeat_pb2
import heartbeat_pb2_grpc

SERVER_ADDRESS = 'localhost:50051' # O mesmo endereço e porta do seu heartbeat_server.py
CLIENT_SERVICE_ID = "test_client_1" # Um ID para este cliente de teste
SEND_INTERVAL = 4 # Segundos (um pouco menos que o HEARTBEAT_EXPECTED_INTERVAL para garantir que chegue)

def send_heartbeats():
    print(f"Tentando conectar ao servidor de Heartbeat em {SERVER_ADDRESS}...")
    try:
        # Criar um canal inseguro para o servidor
        with grpc.insecure_channel(SERVER_ADDRESS) as channel:
            # Criar um stub (cliente)
            stub = heartbeat_pb2_grpc.HeartbeatStub(channel)
            print(f"Conectado! Enviando heartbeats como '{CLIENT_SERVICE_ID}' a cada {SEND_INTERVAL} segundos.")
            print("Pressione Ctrl+C para parar.")
            
            while True:
                try:
                    # Criar a mensagem de requisição
                    request = heartbeat_pb2.HeartbeatRequest(service_id=CLIENT_SERVICE_ID)
                    
                    # Enviar o heartbeat
                    stub.SendHeartbeat(request)
                    print(f"[{time.ctime()}] Heartbeat enviado para {CLIENT_SERVICE_ID}")
                    
                    time.sleep(SEND_INTERVAL)
                
                except grpc.RpcError as e:
                    print(f"Erro ao enviar heartbeat: {e.code()} - {e.details()}")
                    print("Verifique se o servidor de heartbeat está rodando. Tentando reconectar em 5 segundos...")
                    time.sleep(5) # Espera antes de tentar novamente no loop principal do canal
                    break # Sai do loop interno para tentar recriar o canal
                except KeyboardInterrupt:
                    print("\nCliente de teste encerrado pelo usuário.")
                    return
    
    except grpc.FutureTimeoutError:
        print(f"Não foi possível conectar ao servidor {SERVER_ADDRESS}. Servidor offline ou endereço incorreto.")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")

if __name__ == '__main__':
    # Permite alterar o ID do serviço via argumento de linha de comando, se desejado
    if len(sys.argv) > 1:
        CLIENT_SERVICE_ID = sys.argv[1]
        
    while True: # Loop para tentar reconectar caso o canal feche
        send_heartbeats()
        print("Tentando reconectar em 10 segundos caso a conexão tenha sido perdida...")
        time.sleep(10)