PROTOS_DIR = .
PYTHON_OUT_DIR = .

PROTOS = \
	$(PROTOS_DIR)/heartbeat.proto \
	$(PROTOS_DIR)/backup.proto \
	$(PROTOS_DIR)/guiche_info.proto \
	$(PROTOS_DIR)/terminal.proto

GENERATED_PYTHON_FILES = \
	$(PYTHON_OUT_DIR)/heartbeat_pb2.py \
	$(PYTHON_OUT_DIR)/heartbeat_pb2_grpc.py \
	$(PYTHON_OUT_DIR)/backup_pb2.py \
	$(PYTHON_OUT_DIR)/backup_pb2_grpc.py \
	$(PYTHON_OUT_DIR)/guiche_info_pb2.py \
	$(PYTHON_OUT_DIR)/guiche_info_pb2_grpc.py \
	$(PYTHON_OUT_DIR)/terminal_pb2.py \
	$(PYTHON_OUT_DIR)/terminal_pb2_grpc.py

all: $(GENERATED_PYTHON_FILES)

$(PYTHON_OUT_DIR)/%_pb2.py $(PYTHON_OUT_DIR)/%_pb2_grpc.py: $(PROTOS_DIR)/%.proto $(PROTOS)
	python -m grpc_tools.protoc -I$(PROTOS_DIR) --python_out=$(PYTHON_OUT_DIR) --grpc_python_out=$(PYTHON_OUT_DIR) $<

protos: all

clean:
	rm -f $(GENERATED_PYTHON_FILES)

.PHONY: all protos clean
