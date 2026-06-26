.PHONY: build clean test

build:
	go build -o git ./cmd/git/

clean:
	rm -f git

test:
	@echo 'describe:'
	@echo '{"jsonrpc":"2.0","method":"describe","id":1}' | ./git | python3 -m json.tool
	@echo ''
	@echo 'on_shutdown:'
	@echo '{"jsonrpc":"2.0","method":"on_shutdown","id":2}' | ./git
