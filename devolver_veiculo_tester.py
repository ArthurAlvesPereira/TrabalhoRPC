# print("Debugging script para devolver um veículo a um terminal via gRPC")

import grpc
import argparse # Para lidar com argumentos de linha de comando

# Assumindo que seus arquivos .proto compilados (terminal_pb2.py e terminal_pb2_grpc.py)
# estão em um local que o Python pode encontrar (por exemplo, na mesma pasta ou em PYTHONPATH)
import terminal_pb2
import terminal_pb2_grpc

def devolver_veiculo(terminal_address, client_id, vehicle_name):
    """
    Conecta-se a um terminal e envia uma requisição para devolver um veículo.

    Args:
        terminal_address (str): Endereço do terminal (ex: 'localhost:50151').
        client_id (str): ID do cliente que está devolvendo o veículo.
        vehicle_name (str): Nome exato do veículo a ser devolvido.
    """
    print(f"Tentando devolver veículo '{vehicle_name}' pelo cliente '{client_id}' ao terminal {terminal_address}...")
    try:
        # Cria um canal de comunicação com o terminal especificado.
        with grpc.insecure_channel(terminal_address) as channel:
            # Cria um stub (cliente) para o serviço Terminal.
            stub = terminal_pb2_grpc.TerminalStub(channel)

            # Cria a requisição de devolução.
            request = terminal_pb2.ReturnVehicleRequest(
                ID_cliente=client_id,
                nome_veiculo=vehicle_name
            )

            # Chama o RPC ReturnVehicle no servidor do terminal.
            # Adiciona um timeout para a chamada.
            response = stub.ReturnVehicle(request, timeout=10)

            print(f"Resposta do Terminal ({terminal_address}):")
            print(f"  Status: {response.status}")
            print(f"  Mensagem: {response.message}")

    except grpc.RpcError as e:
        print(f"Erro de RPC ao tentar devolver veículo no terminal {terminal_address}:")
        print(f"  Status Code: {e.code()}")
        print(f"  Detalhes: {e.details()}")
    except Exception as e:
        print(f"Um erro inesperado ocorreu: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Script para devolver um veículo a um terminal.")
    parser.add_argument("terminal_address", help="Endereço do terminal (ex: localhost:50151)")
    parser.add_argument("client_id", help="ID do cliente que está devolvendo o veículo")
    parser.add_argument("vehicle_name", help="Nome do veículo a ser devolvido")

    args = parser.parse_args()

    # Chama a função para devolver o veículo com os argumentos fornecidos.
    devolver_veiculo(args.terminal_address, args.client_id, args.vehicle_name)