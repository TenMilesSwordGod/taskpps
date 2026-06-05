#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Building taskpps-agent ==="
go build -v -o taskpps-agent .

echo ""
echo "=== Cross-compiling ==="

PLATFORMS=(
  "linux/amd64"
  "linux/arm64"
)

for platform in "${PLATFORMS[@]}"; do
  IFS="/" read -r GOOS GOARCH <<< "$platform"
  output="build/taskpps-agent-${GOOS}-${GOARCH}"
  echo "Building $output ..."
  GOOS=$GOOS GOARCH=$GOARCH go build -o "$output" .
done

echo ""
echo "=== Build artifacts ==="
ls -lh taskpps-agent
ls -lh build/
