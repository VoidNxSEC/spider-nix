.PHONY: build run test clean deps

BINARY_NAME=spider-network-proxy
MAIN_PATH=./cmd/spider-network-proxy

build:
	@echo "Building $(BINARY_NAME)..."
	go build -o $(BINARY_NAME) $(MAIN_PATH)

run: build
	@echo "Starting proxy..."
	./$(BINARY_NAME) --config configs/production.toml

test:
	@echo "Running tests..."
	go test -v ./...

clean:
	@echo "Cleaning..."
	rm -f $(BINARY_NAME)
	go clean

deps:
	@echo "Downloading dependencies..."
	go mod download
	go mod tidy

install:
	@echo "Installing to /usr/local/bin..."
	sudo cp $(BINARY_NAME) /usr/local/bin/

fmt:
	@echo "Formatting code..."
	go fmt ./...

lint:
	@echo "Linting..."
	go vet ./...
