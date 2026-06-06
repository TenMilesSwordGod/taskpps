#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Update Script (pip + gunicorn)
# ============================================================================
# Usage: sudo ./scripts/update.sh
# Pull latest code, update dependencies, and restart service
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="taskpps"
SERVER_HOME="/opt/taskpps"
VENV_DIR="$SERVER_HOME/server/.venv"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

backup_config() {
    log_step "Backing up configuration..."
    if [[ -f "$SERVER_HOME/taskpps.yaml" ]]; then
        cp "$SERVER_HOME/taskpps.yaml" "$SERVER_HOME/taskpps.yaml.bak.$(date +%Y%m%d_%H%M%S)"
        log_info "Config backed up"
    fi
    if [[ -f "$SERVER_HOME/.taskpps/state.db" ]]; then
        cp "$SERVER_HOME/.taskpps/state.db" "$SERVER_HOME/.taskpps/state.db.bak.$(date +%Y%m%d_%H%M%S)"
        log_info "Database backed up"
    fi
}

update_code() {
    log_step "Updating server code..."

    if [[ -d "$PROJECT_ROOT/.git" ]]; then
        cd "$PROJECT_ROOT"
        git pull origin main || log_warn "Git pull failed, using local files"
    fi

    # Sync server code to server home
    rsync -a --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='pipelines/' \
        --exclude='agents/' \
        --exclude='credentials/' \
        --exclude='tasks/' \
        --exclude='plugins/' \
        "$PROJECT_ROOT/" "$SERVER_HOME/"

    chown -R taskpps:taskpps "$SERVER_HOME"

    # Build and deploy execution agent binary
    if [[ -f "$PROJECT_ROOT/execution_agent/main.go" ]] && command -v go &>/dev/null; then
        log_step "Rebuilding execution agent binary..."
        cd "$PROJECT_ROOT/execution_agent"
        go build -o taskpps-agent .
        mkdir -p build
        GOOS=linux GOARCH=amd64 go build -o build/taskpps-agent-linux-amd64 .
        GOOS=linux GOARCH=arm64 go build -o build/taskpps-agent-linux-arm64 .
        cp -r build "$SERVER_HOME/execution_agent/"
        cp taskpps-agent "$SERVER_HOME/execution_agent/"
        log_info "Agent binary updated"
        cd "$PROJECT_ROOT"
    fi

    # Rebuild ppsctl if source available
    if command -v go &>/dev/null && [[ -f "$SERVER_HOME/cli/main.go" ]]; then
        log_step "Rebuilding ppsctl..."
        cd "$SERVER_HOME/cli"
        go build -o bin/ppsctl .
        cp bin/ppsctl /usr/local/bin/ppsctl 2>/dev/null || true
        cd "$PROJECT_ROOT"
        log_info "ppsctl updated"
    fi

    log_info "Server code updated"
}

update_deps() {
    log_step "Updating dependencies with pip..."

    cd "$SERVER_HOME/server"

    su -s /bin/bash taskpps -c "
        export HOME=/var/lib/taskpps
        source ${VENV_DIR}/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -e '.[dev]'
    "

    log_info "Dependencies updated"
}

restart_service() {
    log_step "Restarting service..."
    systemctl daemon-reload
    systemctl restart "$SERVICE_NAME"

    sleep 3

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "Service restarted successfully!"
    else
        log_error "Service failed to restart!"
        journalctl -u "$SERVICE_NAME" --no-pager -n 30
        exit 1
    fi
}

main() {
    log_info "Starting TaskPPS update (pip + gunicorn)..."

    check_root
    backup_config
    update_code
    update_deps
    restart_service

    log_info "========================================"
    log_info "Update completed successfully!"
    log_info "========================================"
}

main