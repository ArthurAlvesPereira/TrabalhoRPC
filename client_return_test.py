import grpc
import terminal_pb2
import terminal_pb2_grpc
import time

TERMINAL_ADDRESS = 'localhost:50151' # Endereço do seu terminal_1.py
CLIENT_ID = "return_tester_001"
CLIENT_CALLBACK_IP = "localhost" # IP que o terminal usaria para callback
CLIENT_CALLBACK_PORT = "49999"   # Porta de callback fictícia para este teste

def rent_for_return_test(vehicle_class="Executivos"):
    print(f"\n--- {CLIENT_ID}: Tentando ALUGAR um '{vehicle_class}' para depois devolver ---")
    with grpc.insecure_channel(TERMINAL_ADDRESS) as channel:
        stub = terminal_pb2_grpc.TerminalStub(channel)
        request = terminal_pb2.RentCarRequest(
            ID_cliente=CLIENT_ID,
            IP_cliente=CLIENT_CALLBACK_IP, 
            Porta_cliente=CLIENT_CALLBACK_PORT,
            Classe_veiculo=vehicle_class
        )
        try:
            response = stub.RentACar(request)
            print(f"{CLIENT_ID}: Resposta do RentACar: Status='{response.status}', Item='{response.item_name}'")
            if response.status == "CONCLUIDO":
                return response.item_name # Retorna o nome do veículo alugado
        except grpc.RpcError as e:
            print(f"{CLIENT_ID}: Erro RPC no RentACar: {e.details()}")
        return None

def return_vehicle_test(client_id, vehicle_name):
    print(f"\n--- {client_id}: Tentando DEVOLVER o veículo '{vehicle_name}' ---")
    with grpc.insecure_channel(TERMINAL_ADDRESS) as channel:
        stub = terminal_pb2_grpc.TerminalStub(channel)
        request = terminal_pb2.ReturnVehicleRequest(
            ID_cliente=client_id,
            nome_veiculo=vehicle_name
        )
        try:
            response = stub.ReturnVehicle(request)
            print(f"{client_id}: Resposta do ReturnVehicle: Status='{response.status}', Mensagem='{response.message}'")
            return response.status
        except grpc.RpcError as e:
            print(f"{client_id}: Erro RPC no ReturnVehicle: {e.details()}")
        return None

if __name__ == '__main__':
    # 1. Alugar um carro (Ex: um Executivo)
    # Para este teste funcionar, certifique-se que o terminal_1.py tem Executivos disponíveis
    # e que não há muitos clientes do professor rodando e esgotando a frota.
    # Para um teste mais controlado, você pode querer iniciar o terminal_1.py com uma frota "fresca".

    alugado_com_sucesso = False
    veiculo_alugado = None

    # Tentar alugar algumas vezes caso a frota esteja ocupada por outros testes
    for i in range(3): # Tenta alugar um carro algumas vezes
        # Reinicie o terminal_1.py para garantir que a frota está como no início do arquivo para este teste
        print(f"\nAVISO: Para este teste funcionar bem, reinicie o terminal_1.py para resetar a frota.")
        print(f"Tentativa {i+1} de alugar um carro da classe 'Executivos'")
        veiculo_alugado_nome = rent_for_return_test("Executivos")
        if veiculo_alugado_nome:
            alugado_com_sucesso = True
            print(f"SUCESSO AO ALUGAR: Cliente '{CLIENT_ID}' alugou '{veiculo_alugado_nome}'.")
            break
        else:
            print(f"Falha ao tentar alugar 'Executivos' na tentativa {i+1}. Verifique a disponibilidade no terminal_1.py.")
            if i < 2: time.sleep(2) # Pequena pausa antes de tentar novamente

    if not alugado_com_sucesso:
        print("\nNão foi possível alugar um veículo para testar a devolução. Encerrando teste.")
        exit()

    # Simular um tempo de uso
    print(f"\n{CLIENT_ID}: Usando o veículo '{veiculo_alugado_nome}' por alguns segundos...")
    time.sleep(5)

    # 2. Devolver o carro
    status_devolucao = return_vehicle_test(CLIENT_ID, veiculo_alugado_nome)

    if status_devolucao == "DEVOLVIDO_SUCESSO":
        print(f"\nSUCESSO: Veículo '{veiculo_alugado_nome}' devolvido.")
        print("Verifique os logs do terminal_1.py para ver se a lista de espera foi processada e se callbacks foram tentados (se havia clientes esperando por 'Executivos').")
        print("Você também precisaria de um 'cliente servidor de callback' rodando na porta especificada (ex: 4000X) para receber o callback.")
    else:
        print(f"\nFALHA na devolução do veículo '{veiculo_alugado_nome}'. Status: {status_devolucao}")