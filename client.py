import grpc
import guiche_info_pb2
import guiche_info_pb2_grpc
import terminal_pb2
import terminal_pb2_grpc
import threading
from multiprocessing.pool import ThreadPool
import time
import random
from concurrent import futures
import os

INFO_ADDRESS = 'localhost:50051'
nomes = ["Arthur", "Beatriz", "Carolina", "David", "Eduardo", "Fabiana", "Geraldo", "Hector"]

MIN_RENT_TIME = 5 
MAX_RENT_TIME = 15 

def log_client_event(client_id_str, message):
    log_file = f"cliente_{client_id_str}.txt"
    log_entry = f"{time.ctime(time.time())}: {message}\n"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"ERRO ao escrever no log do cliente {client_id_str}: {e}")

class CallbackServiceServicer(terminal_pb2_grpc.CallbackServiceServicer):
    def __init__(self, client_id_str):
        self.client_id_str = client_id_str
        super().__init__()

    def ReceiveCallback(self, request, context):
        message_content = request.message_content
        log_msg = f"Callback recebido: '{message_content}'"
        print(f"\n>>> Cliente {self.client_id_str} (Servidor Callback): Recebeu callback: '{message_content}'")
        log_client_event(self.client_id_str, log_msg)
        return terminal_pb2.CallbackResponse(status="Callback Recebido OK")

def start_client_as_server(port, client_id_str):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    terminal_pb2_grpc.add_CallbackServiceServicer_to_server(CallbackServiceServicer(client_id_str), server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    try:
        server.wait_for_termination()
    except Exception as e:
        print(f"Cliente {client_id_str} (Servidor Callback) interrompido: {e}")

def cliente(requested_class_from_file: str, client_idx: int, unique_id_for_port: int):
    client_name = nomes[client_idx % len(nomes)]
    
    client_ip = 'localhost'
    if unique_id_for_port < 10:
        client_port_str = '4000' + str(unique_id_for_port)
    elif unique_id_for_port < 100:
        client_port_str = '400' + str(unique_id_for_port)
    else:
        client_port_str = '40' + str(unique_id_for_port)

    requested_class = requested_class_from_file.strip()

    print(f">> Cliente {client_name} ({client_ip}:{client_port_str}), buscando veículo da classe '{requested_class}'")
    log_client_event(client_name, f"Iniciando busca por classe '{requested_class}'. Callback server na porta {client_port_str}.")

    callback_server_thread = threading.Thread(target=start_client_as_server, args=(client_port_str, client_name), daemon=True)
    callback_server_thread.start()
    time.sleep(0.2)

    rented_vehicle_name = None
    terminal_aluguel_original = None

    try:
        log_client_event(client_name, f"Requisição enviada ao guichê de informações para aluguel em {time.ctime(time.time())}")
        terminal_contatado_para_aluguel = None
        with grpc.insecure_channel(INFO_ADDRESS) as info_channel:
            info_stub = guiche_info_pb2_grpc.InformationStub(info_channel)
            info_response = info_stub.GetTerminalOnLine(guiche_info_pb2.Empty(), timeout=5)
            terminal_contatado_para_aluguel = info_response.message
            log_client_event(client_name, f"Resposta recebida do guichê de informações em {time.ctime(time.time())}: terminal disponível: {terminal_contatado_para_aluguel}")
            # print(f"Cliente {client_name}: Terminal de locação ativo obtido: {terminal_contatado_para_aluguel}")

        if terminal_contatado_para_aluguel:
            log_client_event(client_name, f"Requisição enviada ao {terminal_contatado_para_aluguel} para classe '{requested_class}' em {time.ctime(time.time())}")
            with grpc.insecure_channel(terminal_contatado_para_aluguel) as rental_channel:
                terminal_stub = terminal_pb2_grpc.TerminalStub(rental_channel)
                rent_request = terminal_pb2.RentCarRequest(
                    ID_cliente=client_name, IP_cliente=client_ip,
                    Porta_cliente=client_port_str, Classe_veiculo=requested_class
                )
                rent_response = terminal_stub.RentACar(rent_request, timeout=10)
                
                status_veiculo_msg = rent_response.item_name if rent_response.status == "CONCLUIDO" else requested_class
                log_client_event(client_name, f"Resposta recebida de {terminal_contatado_para_aluguel}: {rent_response.status} {status_veiculo_msg} em {time.ctime(time.time())}")
                print(f">> Cliente {client_name} obteve resposta do Terminal ({terminal_contatado_para_aluguel}): {rent_response.status} para '{status_veiculo_msg}'")

                if rent_response.status == "CONCLUIDO":
                    rented_vehicle_name = rent_response.item_name
                    terminal_aluguel_original = terminal_contatado_para_aluguel
        else:
            log_client_event(client_name, "Não foi possível obter um terminal ativo do guichê para aluguel.")
            return

    except grpc.RpcError as e:
        error_log_msg = f"Erro de RPC na fase de aluguel: {e.code()} - {e.details()}"
        log_client_event(client_name, error_log_msg)
        print(f"Thread Cliente {client_name}: {error_log_msg}")
        return 
    except Exception as e:
        error_log_msg = f"Erro inesperado na fase de aluguel: {e}"
        log_client_event(client_name, error_log_msg)
        print(f"Thread Cliente {client_name}: {error_log_msg}")
        return

    if rented_vehicle_name and terminal_aluguel_original:
        try:
            usage_time = random.randint(MIN_RENT_TIME, MAX_RENT_TIME)
            log_client_event(client_name, f"Veículo '{rented_vehicle_name}' alugado de {terminal_aluguel_original}. Usando por {usage_time} segundos.")
            print(f"Cliente {client_name}: Veículo '{rented_vehicle_name}' alugado de {terminal_aluguel_original}. Simulando uso por {usage_time}s.")
            time.sleep(usage_time)

            log_client_event(client_name, f"Iniciando devolução do veículo '{rented_vehicle_name}'.")
            print(f"Cliente {client_name}: Iniciando devolução de '{rented_vehicle_name}'.")

            terminal_para_devolucao = terminal_aluguel_original
            devolucao_bem_sucedida = False

            log_client_event(client_name, f"Tentando devolução no terminal original: {terminal_para_devolucao} para veículo '{rented_vehicle_name}' em {time.ctime(time.time())}")
            print(f"Cliente {client_name}: Tentando devolver '{rented_vehicle_name}' no terminal original {terminal_para_devolucao}.")
            try:
                with grpc.insecure_channel(terminal_para_devolucao) as return_channel_orig:
                    return_stub_orig = terminal_pb2_grpc.TerminalStub(return_channel_orig)
                    return_request_orig = terminal_pb2.ReturnVehicleRequest(ID_cliente=client_name, nome_veiculo=rented_vehicle_name)
                    return_response_orig = return_stub_orig.ReturnVehicle(return_request_orig, timeout=10)
                    
                    log_client_event(client_name, f"Resposta de devolução recebida de {terminal_para_devolucao} (original): {return_response_orig.status} - {return_response_orig.message} em {time.ctime(time.time())}")
                    print(f"Cliente {client_name}: Resposta da devolução (original) de '{rented_vehicle_name}' do terminal {terminal_para_devolucao}: {return_response_orig.status} ({return_response_orig.message})")
                    
                    if return_response_orig.status == "DEVOLVIDO_SUCESSO":
                        devolucao_bem_sucedida = True
                
            except grpc.RpcError as e_return_original:
                log_client_event(client_name, f"Erro RPC ao tentar devolução no terminal original {terminal_para_devolucao}: {e_return_original.code()} - {e_return_original.details()}. Tentando guichê.")
                print(f"Cliente {client_name}: Erro RPC ao devolver no terminal original {terminal_para_devolucao}. Tentando guichê.")
            except Exception as e_gen_original:
                log_client_event(client_name, f"Erro inesperado na devolução no terminal original {terminal_para_devolucao}: {e_gen_original}. Tentando guichê.")
                print(f"Cliente {client_name}: Erro inesperado ao devolver no terminal original {terminal_para_devolucao}. Tentando guichê.")

            if not devolucao_bem_sucedida:
                log_client_event(client_name, f"Devolução no terminal original não bem-sucedida. Contatando guichê para novo terminal de devolução em {time.ctime(time.time())}")
                print(f"Cliente {client_name}: Devolução no terminal original falhou. Contatando guichê.")
                
                terminal_alternativo_devolucao = None
                try:
                    with grpc.insecure_channel(INFO_ADDRESS) as info_channel_return_alt:
                        info_stub_return_alt = guiche_info_pb2_grpc.InformationStub(info_channel_return_alt)
                        info_response_return_alt = info_stub_return_alt.GetTerminalOnLine(guiche_info_pb2.Empty(), timeout=5)
                        terminal_alternativo_devolucao = info_response_return_alt.message
                        log_client_event(client_name, f"Resposta recebida do guichê para devolução alternativa em {time.ctime(time.time())}: terminal disponível: {terminal_alternativo_devolucao}")
                        print(f"Cliente {client_name}: Terminal de devolução alternativo (via guichê) obtido: {terminal_alternativo_devolucao}")
                except grpc.RpcError as e_info_return_alt:
                    log_client_event(client_name, f"Erro RPC ao contatar guichê para terminal de devolução alternativo: {e_info_return_alt.code()} - {e_info_return_alt.details()}. Devolução de '{rented_vehicle_name}' falhou.")
                    print(f"Cliente {client_name}: Erro ao contatar guichê para terminal alternativo. Devolução de '{rented_vehicle_name}' falhou.")
                    return

                if terminal_alternativo_devolucao:
                    log_client_event(client_name, f"Requisição de devolução enviada ao terminal alternativo {terminal_alternativo_devolucao} para veículo '{rented_vehicle_name}' em {time.ctime(time.time())}")
                    print(f"Cliente {client_name}: Tentando devolver '{rented_vehicle_name}' no terminal alternativo {terminal_alternativo_devolucao}.")
                    try:
                        with grpc.insecure_channel(terminal_alternativo_devolucao) as return_channel_alt:
                            return_stub_alt = terminal_pb2_grpc.TerminalStub(return_channel_alt)
                            return_request_alt = terminal_pb2.ReturnVehicleRequest(ID_cliente=client_name, nome_veiculo=rented_vehicle_name)
                            return_response_alt = return_stub_alt.ReturnVehicle(return_request_alt, timeout=10)
                            
                            log_client_event(client_name, f"Resposta de devolução recebida de {terminal_alternativo_devolucao} (alternativo): {return_response_alt.status} - {return_response_alt.message} em {time.ctime(time.time())}")
                            print(f"Cliente {client_name}: Resposta da devolução (alternativo) de '{rented_vehicle_name}' do terminal {terminal_alternativo_devolucao}: {return_response_alt.status} ({return_response_alt.message})")
                    except grpc.RpcError as e_return_alt:
                        log_client_event(client_name, f"Erro RPC na devolução (alternativo) no terminal {terminal_alternativo_devolucao} para '{rented_vehicle_name}': {e_return_alt.code()} - {e_return_alt.details()}")
                        print(f"Thread Cliente {client_name}: Erro RPC na devolução (alternativo) em {terminal_alternativo_devolucao}: {e_return_alt.details()}")
                    except Exception as e_gen_alt:
                        log_client_event(client_name, f"Erro inesperado na devolução (alternativo) no terminal {terminal_alternativo_devolucao} para '{rented_vehicle_name}': {e_gen_alt}")
                        print(f"Thread Cliente {client_name}: Erro inesperado na devolução (alternativo) em {terminal_alternativo_devolucao}: {e_gen_alt}")
                else: 
                     log_client_event(client_name, f"Não foi possível obter um terminal (via guichê) para devolução do veículo '{rented_vehicle_name}'. Devolução falhou.")
                     print(f"Cliente {client_name}: FALHA CRÍTICA - Não foi possível obter um terminal (via guichê) para devolução de '{rented_vehicle_name}'.")


        except Exception as e_geral_devolucao:
            log_client_event(client_name, f"Erro geral durante o processo de devolução do veículo '{rented_vehicle_name}': {e_geral_devolucao}")
            print(f"Cliente {client_name}: Erro geral no processo de devolução: {e_geral_devolucao}")

    time.sleep(1) 
def main():
    num_threads = 31 
    carros_file = 'carros_solicitados.txt'
    lines = []
    try:
        with open(carros_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"Erro: O arquivo '{carros_file}' não foi encontrado.")
        return
    except Exception as e:
        print(f"Erro ao ler o arquivo '{carros_file}': {e}")
        return

    if not lines:
        print(f"Atenção: O arquivo '{carros_file}' está vazio ou não contém classes válidas.")
        return

    client_names_in_run = set()
    for i in range(len(lines)):
        client_names_in_run.add(nomes[i % len(nomes)])
    
    for name_to_clear in client_names_in_run:
        log_file_cliente_simple = f"cliente_{name_to_clear}.txt"
        if os.path.exists(log_file_cliente_simple):
            try:
                os.remove(log_file_cliente_simple)
            except OSError as e:
                print(f"Não foi possível remover o log antigo {log_file_cliente_simple}: {e}")


    actual_num_threads = min(num_threads, len(lines))
    print(f"\nProcessando {len(lines)} requisições com até {actual_num_threads} threads simultâneas.")

    with ThreadPool(processes=actual_num_threads) as pool:
        print("ThreadPool criado. Submetendo tarefas gRPC...")
        
        client_tasks_futures = []
        for i, requested_class_from_file in enumerate(lines):
            future = pool.apply_async(cliente, (requested_class_from_file, i % len(nomes), i))
            client_tasks_futures.append(future)
        
        print(f"{len(client_tasks_futures)} tarefas submetidas. Aguardando conclusão...")

        for i, f_result in enumerate(client_tasks_futures):
            try:
                f_result.get(timeout= (MAX_RENT_TIME * 2) + 40 )
            except TimeoutError:
                print(f"AVISO: Tarefa do cliente para '{lines[i]}' (cliente '{nomes[i%len(nomes)]}') excedeu o tempo limite.")
            except Exception as exc:
                print(f"ERRO: Requisição para '{lines[i]}' (cliente '{nomes[i%len(nomes)]}') gerou uma exceção: {exc}")
        
        print("Todas as tarefas dos clientes foram submetidas e a ThreadPool aguardou sua possível conclusão (com timeout).")

    print("Programa cliente principal quase finalizado. Aguardando um pouco para callbacks pendentes...")
    time.sleep(20)
    print("Encerrando cliente.")

if __name__ == '__main__':
    main()