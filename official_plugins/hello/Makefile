.PHONY: build clean test

build:
	go build -o hello ./cmd/hello/

clean:
	rm -f hello

test:
	echo '{"jsonrpc":"2.0","method":"describe","id":1}' | ./hello
