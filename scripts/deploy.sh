#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Deployment Script (pip + gunicorn)
# ============================================================================
# Usage: sudo ./scripts/deploy.sh [install|uninstall|status|restart|logs]
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="taskpps"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="/opt/taskpps/server/.venv"
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"

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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Detect OS and package manager
detect_os() {
    if command -v apt-get &>/dev/null; then
        echo "debian"
    elif command -v yum &>/dev/null; then
        echo "rhel"
    elif command -v dnf &>/dev/null; then
        echo "rhel"
    elif command -v pacman &>/dev/null; then
        echo "arch"
    else
        echo "unknown"
    fi
}

# Install Python and system dependencies
install_python_deps() {
    local os_type
    os_type=$(detect_os)

    log_step "Installing Python and system dependencies..."

    case $os_type in
        debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv python3-dev curl rsync gcc
            ;;
        rhel)
            yum install -y python3 python3-pip python3-devel curl rsync gcc
            ;;
        arch)
            pacman -Sy --noconfirm python python-pip curl rsync gcc
            ;;
        *)
            log_warn "Unknown OS, assuming Python 3 is already installed"
            ;;
    esac

    # Upgrade pip to latest and set China mirror globally
    log_step "Configuring pip with China mirror..."
    pip3 config set global.index-url "$PIP_MIRROR" 2>/dev/null || true
}

# Create system user
create_user() {
    if ! id -u taskpps &>/dev/null; then
        log_step "Creating system user 'taskpps'..."
        useradd --system --user-group --home-dir /var/lib/taskpps --shell /bin/bash taskpps
    else
        log_info "System user 'taskpps' already exists"
    fi
}

# Setup project directories
setup_directories() {
    log_step "Setting up project directories..."

    local dirs=(
        "/var/lib/taskpps"
        "/var/log/taskpps"
        "/etc/taskpps"
        "/opt/taskpps"
    )

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
        chown taskpps:taskpps "$dir"
        chmod 750 "$dir"
    done

    # Copy project files
    log_step "Copying project files to /opt/taskpps..."
    rsync -a --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='.venv' \
        --exclude='node_modules' \
        "$PROJECT_ROOT/" /opt/taskpps/

    chown -R taskpps:taskpps /opt/taskpps

    # Build execution agent binary if source is available
    if [[ -f "$PROJECT_ROOT/execution_agent/main.go" ]]; then
        log_step "Building execution agent binary..."
        cd "$PROJECT_ROOT/execution_agent"
        if command -v go &>/dev/null; then
            go build -o taskpps-agent .
            mkdir -p build
            GOOS=linux GOARCH=amd64 go build -o build/taskpps-agent-linux-amd64 .
            GOOS=linux GOARCH=arm64 go build -o build/taskpps-agent-linux-arm64 .
            cp -r build /opt/taskpps/execution_agent/
            cp taskpps-agent /opt/taskpps/execution_agent/
            log_info "Agent binary built and deployed"
        else
            log_warn "Go compiler not found — agent bootstrap will use pre-built binaries if available"
        fi
        cd "$PROJECT_ROOT"
    fi
}

# Install Python dependencies with pip + venv
install_project_deps() {
    log_step "Creating virtual environment and installing dependencies..."

    cd /opt/taskpps/server

    # Remove old venv/uv artifacts if any
    rm -rf .venv .uv.lock

    # Create venv as taskpps user
    su -s /bin/bash taskpps -c "
        export HOME=/var/lib/taskpps
        cd /opt/taskpps/server
        python3 -m venv ${VENV_DIR}
        source ${VENV_DIR}/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -r requirements.txt || pip install -e '.[dev]'
    "

    chown -R taskpps:taskpps /opt/taskpps/server/.venv
    log_info "Dependencies installed successfully"
}

# Generate systemd service file (gunicorn + uvicorn worker)
generate_service_file() {
    log_step "Generating systemd service file (gunicorn)..."

    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=TaskPPS Pipeline Server (Gunicorn)
Documentation=https://github.com/liheng/taskpps
After=network.target
Wants=network.target

[Service]
Type=simple
User=taskpps
Group=taskpps
WorkingDirectory=/opt/taskpps/server
Environment=PYTHONPATH=/opt/taskpps/server
Environment=PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/var/lib/taskpps
Environment=TASKPPS_CONFIG=/opt/taskpps/taskpps.yaml

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/taskpps /var/log/taskpps /opt/taskpps
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitInterval=60s
StartLimitBurst=3

# Graceful shutdown
TimeoutStopSec=30
KillSignal=SIGTERM

ExecStart=${VENV_DIR}/bin/gunicorn \\
    taskpps.main:app \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 0.0.0.0:26521 \\
    --workers 2 \\
    --worker-tmp-dir /dev/shm \\
    --timeout 120 \\
    --graceful-timeout 30 \\
    --access-logfile /var/log/taskpps/access.log \\
    --error-logfile /var/log/taskpps/error.log \\
    --log-level info \\
    --capture-output

ExecReload=/bin/kill -HUP \$MAINPID

[Install]
WantedBy=multi-user.target
EOF

    chmod 644 "$SERVICE_FILE"
    log_info "Service file created at $SERVICE_FILE"
}

# Generate default config
generate_config() {
    local config_file="/opt/taskpps/taskpps.yaml"

    if [[ -f "$config_file" ]]; then
        log_info "Config file already exists, skipping"
        return
    fi

    log_step "Generating default configuration..."

    local api_key
    api_key=$(openssl rand -hex 32)

    cat > "$config_file" << EOF
# TaskPPS Server Configuration
# Generated on $(date -Iseconds)

locale: zh

server:
  host: 0.0.0.0
  port: 26521
  api_key: "$api_key"

executor:
  default_timeout: 3600
  max_workers: 10
  shell: /bin/bash

plugins:
  paths:
    - plugins

triggers: []

env: {}
EOF

    chown taskpps:taskpps "$config_file"
    chmod 640 "$config_file"

    log_info "Default config created at $config_file"
    log_warn "IMPORTANT: API Key generated: $api_key"
    log_warn "Please save this key or update the config file"
}

# Reload systemd and enable service
enable_service() {
    log_step "Enabling systemd service..."
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
}

# Start service
start_service() {
    log_step "Starting $SERVICE_NAME service..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl start "$SERVICE_NAME"
    sleep 3

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "Service started successfully!"
        systemctl status "$SERVICE_NAME" --no-pager
    else
        log_error "Service failed to start!"
        journalctl -u "$SERVICE_NAME" --no-pager -n 30
        exit 1
    fi
}

# Stop service
stop_service() {
    log_step "Stopping $SERVICE_NAME service..."
    systemctl stop "$SERVICE_NAME" || true
}

# Uninstall service
uninstall_service() {
    log_warn "Uninstalling TaskPPS service..."

    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload

    log_info "Service uninstalled"
    log_warn "Project files at /opt/taskpps were NOT removed"
    log_warn "Data at /var/lib/taskpps and /var/log/taskpps were NOT removed"
}

# Show service status
show_status() {
    systemctl status "$SERVICE_NAME" --no-pager
}

# Show logs
show_logs() {
    journalctl -u "$SERVICE_NAME" --no-pager -f
}

# Restart service
restart_service() {
    log_step "Restarting $SERVICE_NAME service..."
    systemctl restart "$SERVICE_NAME"
    sleep 1
    show_status
}

# Full installation
install() {
    log_info "Starting TaskPPS deployment (pip + gunicorn)..."
    log_info "Project root: $PROJECT_ROOT"

    check_root
    install_python_deps
    create_user
    setup_directories
    install_project_deps
    generate_service_file
    generate_config
    enable_service
    start_service

    log_info "========================================"
    log_info "Deployment completed successfully!"
    log_info "========================================"
    log_info "Service:    systemctl status $SERVICE_NAME"
    log_info "Logs:       journalctl -u $SERVICE_NAME -f"
    log_info "Access log: tail -f /var/log/taskpps/access.log"
    log_info "Error log:  tail -f /var/log/taskpps/error.log"
    log_info "Config:     /opt/taskpps/taskpps.yaml"
    log_info "Data:       /var/lib/taskpps"
    log_info "Logs dir:   /var/log/taskpps"
    log_info ""
    log_info "Endpoints:"
    log_info "  API:       http://$(hostname -I | awk '{print $1}'):26521/api"
    log_info "  Agent WS:  ws://$(hostname -I | awk '{print $1}'):26521/api/ws/agent"
    log_info "  Health:    http://$(hostname -I | awk '{print $1}'):26521/api/health"
}

# Main
case "${1:-install}" in
    install)
        install
        ;;
    uninstall)
        check_root
        uninstall_service
        ;;
    status)
        show_status
        ;;
    restart)
        check_root
        restart_service
        ;;
    logs)
        show_logs
        ;;
    stop)
        check_root
        stop_service
        ;;
    start)
        check_root
        start_service
        ;;
    *)
        echo "Usage: $0 [install|uninstall|status|restart|logs|stop|start]"
        echo ""
        echo "Commands:"
        echo "  install    - Full installation with systemd (default)"
        echo "  uninstall  - Remove systemd service"
        echo "  status     - Show service status"
        echo "  restart    - Restart the service"
        echo "  logs       - Follow service logs"
        echo "  stop       - Stop the service"
        echo "  start      - Start the service"
        exit 1
        ;;
esac
