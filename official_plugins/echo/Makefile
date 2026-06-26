.PHONY: build clean test

build:
	go build -o echo ./cmd/echo/

clean:
	rm -f echo

test:
	@echo 'describe:'
	@echo '{"jsonrpc":"2.0","method":"describe","id":1}' | ./echo | python3 -m json.tool
	@echo ''
	@echo 'execute:'
	@printf '{"jsonrpc":"2.0","method":"execute","params":{"message":"hello"},"id":2}\n{"jsonrpc":"2.0","method":"on_shutdown","id":3}\n' | ./echo
