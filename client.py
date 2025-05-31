import grpc
import guiche_info_pb2
import guiche_info_pb2_grpc

import terminal_pb2
import terminal_pb2_grpc

import threading
from multiprocessing.pool import ThreadPool
import time
from concurrent import futures


INFO_ADDRESS = 'localhost:50051'

nomes = ["Alice", "Bob", "Charlie", "David", "Eve","Nick", "Ema", "Maria"]


# Implementação do CallbackService (o cliente atua como servidor aqui)
class CallbackServiceServicer(terminal_pb2_grpc.CallbackServiceServicer):
    def ReceiveCallback(self, request, context):
        """
        Implementa o método ReceiveCallback.
        Recebe uma mensagem de callback do servidor principal.
        """
        message_content = request.message_content
        print(f"\nCliente (Servidor Callback): Recebeu callback: '{message_content}'")
        return terminal_pb2_grpc.CallbackResponse(status="Callback Recebido OK")




# Função para iniciar o servidor gRPC do cliente em um thread separado
def start_client_as_server(port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1)) # Apenas 1 worker para este exemplo
    terminal_pb2_grpc.add_CallbackServiceServicer_to_server(CallbackServiceServicer(), server)
    server.add_insecure_port(f'[::]:{port}')
    print(f"Cliente (Servidor Callback) iniciado na porta {port}...")
    server.start()
    # Mantém o servidor em execução até que o thread seja interrompido
    try:
        server.wait_for_termination()
    except Exception as e:
        print(f"Cliente (Servidor Callback) interrompido: {e}")


def cliente(classe: str,ind: int, i: int):
    """
    Produz chamadas gRPC para guiche de infor e terminal de locação

    Args:
        classe (str): classe solicitada.
        ind (int): um valor derivado de i % 8, apenas para definir um nome ao cliente.
        i (int): valor que define a porta do cliente para call back
    """

    #meu IP e porta (para call back)

    IP='localhost'
    if i<10:
        Porta='4000'+str(i)
    elif i<100:
        Porta='400'+str(i)
    elif i<1000:
        Porta='40'+str(i)
    print (f">> cliente {nomes[ind]} ({IP}:{Porta}), buscando veiculo de classe {classe}")
    # Inicia o servidor gRPC do cliente em um thread separado
    server_thread = threading.Thread(target=start_client_as_server, args=(Porta,), daemon=True)
    server_thread.start()
    time.sleep(1)
    """
    classe: classe de veiculo solicitada
    """
    try:
        # Cria um canal de comunicação com o guiche de informações.
        with grpc.insecure_channel(INFO_ADDRESS) as info:
            stub_info = guiche_info_pb2_grpc.InformationStub(info)
            response = stub_info.GetTerminalOnLine(guiche_info_pb2.Empty())
            print("Terminal ativo: " + response.message)



        # Cria um canal de comunicação com o terminal de trabalho da locadora.
        with grpc.insecure_channel(response.message) as channel:
            stub_terminal = terminal_pb2_grpc.TerminalStub(channel)

            # Enviamensagem de requisição com o nome fornecido e classe solicitada.
            request = terminal_pb2.RentCarRequest(ID_cliente=nomes[ind],IP_cliente=IP,Porta_cliente=Porta,Classe_veiculo=classe)
            response = stub_terminal.RentACar(request)

            print(f">> Cliente {nomes[ind]} obteve resposta do Terminal:{response.status}")
            #if request.status == "CONCLUIDO":
                #aguarda tempo aleatorio
                #contato com info
                #envia msg para devolução do veiculo


    except grpc.RpcError as e:
        # Captura erros específicos do gRPC.
        print(f"Thread  {nomes[ind]}: Erro de RPC: {e.code()} - {e.details()}")
    except Exception as e:
        print(f"Thread para {nomes[ind]}: Erro inesperado: {e}")



def main():
    num_threads = 5

    lines = []
    try:
        with open('carros_solicitados.txt', 'r') as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("Erro: O arquivo 'carros_solicitados.txt' não foi encontrado.")
        return
    except Exception as e:
        print(f"Erro ao ler o arquivo 'carros_solicitados.txt': {e}")
        return

    if not lines:
        print("Atenção: O arquivo 'carros_solicitados.txt' está vazio ou não contém classes válidas.")
        return


    f = open('carros_solicitados.txt', 'r')
    lines = f.readlines()



    print(f"\nProcessando {len(lines)} requisições com até {num_threads} threads simultâneas.")

    # Change: Use ThreadPool from multiprocessing.pool
    # 'processes' argument is used for ThreadPool, not 'max_workers'
    with ThreadPool(processes=num_threads) as pool:
        print("ThreadPool criado. Submetendo tarefas gRPC com apply_async...")
        # Change: Use apply_async and store AsyncResult objects
        client_results = [pool.apply_async(cliente, (lines[i], i % 8, i)) for i in range(len(lines))]
        for i, result_async in enumerate(client_results):
                try:
                    # .get() will block until the result is ready and re-raise exceptions
                    result = result_async.get()
                    #print(f"Resultado da requisição {i}: {result}")
                except Exception as exc:
                    print(f"Requisição {i} gerou uma exceção ao obter o resultado: {exc}")

if __name__ == '__main__':
    main()
'''
os clientes utilizam portas entre:
40000 a 50000
'''

