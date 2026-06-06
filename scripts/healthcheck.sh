#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Health Check Script
# ============================================================================
# Usage: ./scripts/healthcheck.sh [--json]
# Returns 0 if healthy, 1 if unhealthy
# ============================================================================

SERVICE_NAME="taskpps"
API_URL="http://127.0.0.1:26521/api/health"
SERVER_HOME="/opt/taskpps"
JSON_OUTPUT=false

# Parse args
for arg in "$@"; do
    case $arg in
        --json)
            JSON_OUTPUT=true
            ;;
    esac
done

# Colors (only for non-json)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC}  $1"; }

HEALTHY=true
RESULTS=()

check_service() {
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        RESULTS+=("service:ok")
        $JSON_OUTPUT || log_ok "Systemd service is running"
    else
        RESULTS+=("service:failed")
        $JSON_OUTPUT || log_fail "Systemd service is not running"
        HEALTHY=false
    fi
}

check_api() {
    local response
    local http_code

    response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL" 2>/dev/null || echo "000")

    if [[ "$response" == "200" ]]; then
        RESULTS+=("api:ok")
        $JSON_OUTPUT || log_ok "API health endpoint responding (HTTP 200)"
    else
        RESULTS+=("api:failed")
        $JSON_OUTPUT || log_fail "API health endpoint not responding (HTTP $response)"
        HEALTHY=false
    fi
}

check_disk() {
    local usage
    usage=$(df /var/lib/taskpps 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")

    if [[ "$usage" -lt 80 ]]; then
        RESULTS+=("disk:ok")
        $JSON_OUTPUT || log_ok "Disk usage: ${usage}%"
    elif [[ "$usage" -lt 90 ]]; then
        RESULTS+=("disk:warning")
        $JSON_OUTPUT || log_warn "Disk usage: ${usage}%"
    else
        RESULTS+=("disk:critical")
        $JSON_OUTPUT || log_fail "Disk usage: ${usage}%"
        HEALTHY=false
    fi
}

check_memory() {
    local mem_info
    mem_info=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}' 2>/dev/null || echo "0")

    if [[ "$mem_info" -lt 80 ]]; then
        RESULTS+=("memory:ok")
        $JSON_OUTPUT || log_ok "Memory usage: ${mem_info}%"
    elif [[ "$mem_info" -lt 90 ]]; then
        RESULTS+=("memory:warning")
        $JSON_OUTPUT || log_warn "Memory usage: ${mem_info}%"
    else
        RESULTS+=("memory:critical")
        $JSON_OUTPUT || log_fail "Memory usage: ${mem_info}%"
        HEALTHY=false
    fi
}

check_db() {
    local db_path="$SERVER_HOME/.taskpps/state.db"

    if [[ -f "$db_path" ]]; then
        RESULTS+=("database:ok")
        $JSON_OUTPUT || log_ok "Database file exists at $db_path"
    else
        RESULTS+=("database:failed")
        $JSON_OUTPUT || log_fail "Database file not found at $db_path"
        HEALTHY=false
    fi
}

# Run checks
check_service
check_api
check_disk
check_memory
check_db

# Output
if $JSON_OUTPUT; then
    status="healthy"
    $HEALTHY || status="unhealthy"
    echo "{"
    echo "  \"status\": \"$status\","
    echo "  \"timestamp\": \"$(date -Iseconds)\","
    echo "  \"checks\": {"
    for result in "${RESULTS[@]}"; do
        key="${result%%:*}"
        value="${result#*:}"
        echo "    \"$key\": \"$value\""
    done
    echo "  }"
    echo "}"
else
    echo ""
    if $HEALTHY; then
        echo -e "${GREEN}Overall: HEALTHY${NC}"
    else
        echo -e "${RED}Overall: UNHEALTHY${NC}"
    fi
fi

$HEALTHY && exit 0 || exit 1