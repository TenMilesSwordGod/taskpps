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
VENV_DIR="/opt/taskpps/server/.venv"

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
    if [[ -f /opt/taskpps/taskpps.yaml ]]; then
        cp /opt/taskpps/taskpps.yaml /opt/taskpps/taskpps.yaml.bak.$(date +%Y%m%d_%H%M%S)
        log_info "Config backed up"
    fi
}

update_code() {
    log_step "Updating project files..."

    # Check if project root is a git repo
    if [[ -d "$PROJECT_ROOT/.git" ]]; then
        cd "$PROJECT_ROOT"
        git pull origin main || log_warn "Git pull failed, using local files"
    fi

    # Sync files
    rsync -a --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='.venv' \
        --exclude='node_modules' \
        "$PROJECT_ROOT/" /opt/taskpps/

    chown -R taskpps:taskpps /opt/taskpps
    log_info "Project files updated"
}

update_deps() {
    log_step "Updating dependencies with pip..."

    cd /opt/taskpps/server

    su -s /bin/bash taskpps -c "
        export HOME=/var/lib/taskpps
        source ${VENV_DIR}/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -r requirements.txt 2>/dev/null || pip install -e '.[dev]'
    "

    log_info "Dependencies updated"
}

restart_service() {
    log_step "Restarting gunicorn service..."
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
