#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Deployment Script (pip + gunicorn)
# ============================================================================
# Usage: sudo ./scripts/deploy.sh [install|uninstall|status|restart|logs] [--workdir <path>]
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="taskpps"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="/opt/taskpps/server/.venv"
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
SERVER_HOME="/opt/taskpps"
WORKDIR=""

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

# Detect existing project workdir from taskpps.yaml
# NOTE: log messages go to stderr (>&2) because this function is called
# via $(...) command substitution and only the path should be on stdout.
detect_existing_workdir() {
    local detected=""
    local candidate_configs=(
        "$SERVER_HOME/.taskpps/taskpps.yaml"
        "$SERVER_HOME/taskpps.yaml"
        "$PROJECT_ROOT/.taskpps/taskpps.yaml"
        "$PROJECT_ROOT/taskpps.yaml"
    )

    for cfg in "${candidate_configs[@]}"; do
        if [[ -f "$cfg" ]]; then
            local val
            val=$(grep -E '^[[:space:]]*workdir[[:space:]]*:' "$cfg" 2>/dev/null | \
                  head -n1 | sed -E 's/^[[:space:]]*workdir[[:space:]]*:[[:space:]]*//' | \
                  tr -d '"'"'")
            if [[ -n "$val" && -d "$val" ]]; then
                detected="$val"
                echo -e "${GREEN}[INFO]${NC}  检测到已有项目配置: $cfg" >&2
                echo "$detected"
                return
            fi
        fi
    done
    echo ""
}

# Select project workdir
select_workdir() {
    if [[ -n "${WORKDIR:-}" ]]; then
        log_info "Using workdir from --workdir parameter: $WORKDIR"
        return
    fi

    if [[ ! -t 0 ]]; then
        log_info "Non-interactive mode, using default workdir: $SERVER_HOME"
        WORKDIR="$SERVER_HOME"
        return
    fi

    local existing_workdir
    existing_workdir=$(detect_existing_workdir)

    echo ""
    echo "请选择项目工作目录 (pipelines/agents/credentials 存放位置):"

    if [[ -n "$existing_workdir" ]]; then
        echo "  0) 复用已有项目目录 - $existing_workdir (从 taskpps.yaml 检测到)"
    fi

    echo "  1) 默认 - $SERVER_HOME (传统模式，服务器代码与项目文件在同一目录)"
    echo "  2) 当前目录 - $PROJECT_ROOT (git clone 目录)"
    echo "  3) 自定义路径"

    if [[ -n "$existing_workdir" ]]; then
        echo -n "请输入选项 [0/1/2/3] (默认: 0): "
    else
        echo -n "请输入选项 [1/2/3] (默认: 1): "
    fi
    read -r choice

    if [[ -n "$existing_workdir" && ("${choice:-0}" == "0" || "${choice:-0}" == "") ]]; then
        WORKDIR="$existing_workdir"
        log_info "已选择复用已有项目目录: $WORKDIR"
        echo ""
        return
    fi

    case "${choice:-1}" in
        1)
            WORKDIR="$SERVER_HOME"
            log_info "已选择默认模式: $WORKDIR"
            ;;
        2)
            WORKDIR="$PROJECT_ROOT"
            log_info "已选择当前目录: $WORKDIR"
            ;;
        3)
            echo -n "请输入项目工作目录的绝对路径: "
            read -r custom_path
            if [[ -z "$custom_path" ]]; then
                log_error "路径不能为空"
                exit 1
            fi
            WORKDIR="$custom_path"
            log_info "已选择自定义路径: $WORKDIR"
            ;;
        *)
            WORKDIR="$SERVER_HOME"
            log_info "无效选项，使用默认模式: $WORKDIR"
            ;;
    esac

    echo ""
}

# Setup project directories
setup_directories() {
    log_step "Setting up project directories..."

    local dirs=(
        "/var/lib/taskpps"
        "/var/log/taskpps"
        "/etc/taskpps"
        "$SERVER_HOME"
    )

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
        chown taskpps:taskpps "$dir"
        chmod 750 "$dir"
    done

    # Copy project files to server home
    log_step "Copying project files to $SERVER_HOME..."
    # NOTE: exclude .taskpps (workspaces/logs/runtime data) — never overwrite
    # runtime workspaces in $SERVER_HOME, and don't let --delete wipe them
    # (workspaces contain cloned git repos with read-only objects).
    rsync -a --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='.taskpps' \
        "$PROJECT_ROOT/" "$SERVER_HOME/"

    chown -R taskpps:taskpps "$SERVER_HOME"

    # Create server data directory
    mkdir -p "$SERVER_HOME/.taskpps"
    chown -R taskpps:taskpps "$SERVER_HOME/.taskpps"
    chmod 750 "$SERVER_HOME/.taskpps"

    # Always create project structure in workdir (including logs and workspaces)
    log_step "Creating project structure in workdir: $WORKDIR"
    mkdir -p "$WORKDIR"
    chown taskpps:taskpps "$WORKDIR"
    # 2777 = setgid + rwx for owner/group/other. The workdir is intentionally
    # world-writable: any logged-in user (aba, dady, vncuser, ...) can create,
    # edit, and remove files in this project folder without per-user setup.
    # setgid is kept so new files/dirs inherit the `taskpps` group, which
    # keeps the service happy and makes `ls -l` consistent across users.
    chmod 2777 "$WORKDIR"

    # Ensure taskpps user can traverse from / to the workdir.
    # Parent directories need at least 'x' (traverse/execute) permission for 'others'.
    # This is especially important for paths under /home where user home dirs are 700.
    # Permission string format: drwxr-xr-x  (positions 0-9, position 9 = others execute)
    local check_path="$WORKDIR"
    while [[ "$check_path" != "/" ]]; do
        if [[ -d "$check_path" ]]; then
            local perms
            perms=$(stat -c '%A' "$check_path" 2>/dev/null || echo "----------")
            if [[ "${perms:9:1}" != "x" && "${perms:9:1}" != "t" ]]; then
                log_warn "父目录 $check_path 对其他用户无遍历权限 (当前 $perms),正在添加 o+x..."
                chmod o+x "$check_path" 2>/dev/null || log_warn "  无法修改 $check_path 权限,请手动确认 taskpps 用户可访问"
            fi
        fi
        check_path=$(dirname "$check_path")
    done

    local project_dirs=(
        "pipelines"
        "agents"
        "credentials"
        "tasks"
        "plugins"
        ".taskpps"
        ".taskpps/logs"
        ".taskpps/workspaces"
    )

    for d in "${project_dirs[@]}"; do
        mkdir -p "$WORKDIR/$d"
        chown taskpps:taskpps "$WORKDIR/$d"
        # 2777 = world-writable + setgid, see comment on $WORKDIR above.
        chmod 2777 "$WORKDIR/$d"
        log_info "  created $WORKDIR/$d"
    done

    # Recursively fix ownership of pre-existing runtime data (e.g. state.db
    # created by a prior local run under a different user) so the service
    # running as 'taskpps' can write to it. Without this, SQLite reports
    # "attempt to write a readonly database" on the first write attempt.
    if [[ -d "$WORKDIR/.taskpps" ]]; then
        chown -R taskpps:taskpps "$WORKDIR/.taskpps"
        # Ensure existing subdirs under .taskpps are also world-writable so
        # any user can drop into workspaces/ or read logs/ without setup.
        find "$WORKDIR/.taskpps" -type d -exec chmod 2777 {} +
    fi
}

# Install Python dependencies with pip + venv
install_project_deps() {
    log_step "Creating virtual environment and installing dependencies..."

    cd "$SERVER_HOME/server"

    # Remove old venv/uv artifacts if any
    rm -rf .venv .uv.lock

    # Create venv as taskpps user
    su -s /bin/bash taskpps -c "
        export HOME=/var/lib/taskpps
        cd $SERVER_HOME/server
        python3 -m venv ${VENV_DIR}
        source ${VENV_DIR}/bin/activate
        pip install --upgrade pip setuptools wheel
        pip install -e '.[dev]'
    "

    chown -R taskpps:taskpps "$SERVER_HOME/server/.venv"
    log_info "Dependencies installed successfully"
}

# Build Web UI
build_web_ui() {
    log_step "Building Web UI..."

    local web_dir="$SERVER_HOME/web"

    if [[ ! -f "$web_dir/package.json" ]]; then
        log_warn "Web UI source not found at $web_dir, skipping build"
        return
    fi

    # 检查 Node.js 是否可用
    if ! command -v node &>/dev/null; then
        log_warn "Node.js not found, installing..."
        local os_type
        os_type=$(detect_os)
        case $os_type in
            debian)
                apt-get install -y -qq nodejs npm 2>/dev/null || {
                    # 尝试 NodeSource（使用清华镜像）
                    curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/nodesource/deb_20.x/setup_20.x | bash -
                    apt-get install -y -qq nodejs
                }
                ;;
            rhel)
                yum install -y nodejs npm 2>/dev/null || {
                    curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/nodesource/rpm_20.x/setup_20.x | bash -
                    yum install -y nodejs
                }
                ;;
            *)
                log_error "Cannot install Node.js automatically on this OS. Please install Node.js 18+ manually and re-run."
                return
                ;;
        esac
    fi

    log_info "Node.js version: $(node --version)"
    log_info "npm version: $(npm --version)"

    cd "$web_dir"

    # 配置 npm 中国镜像
    log_info "Configuring npm with China mirror..."
    npm config set registry https://registry.npmmirror.com

    # 安装依赖并构建
    npm install --prefer-offline 2>&1 | tail -5
    npm run build 2>&1 | tail -10

    if [[ -d "$web_dir/dist" ]]; then
        chown -R taskpps:taskpps "$web_dir/dist"
        log_info "Web UI built successfully → $web_dir/dist"
    else
        log_error "Web UI build failed — dist/ not found"
    fi

    # 清理 node_modules 减小部署体积
    rm -rf "$web_dir/node_modules"
    log_info "Cleaned up node_modules"
}

# Generate systemd service file (gunicorn + uvicorn worker)
generate_service_file() {
    log_step "Generating systemd service file (gunicorn)..."

    # ProtectHome=true makes /home empty and inaccessible.
    # If workdir is under /home, we must relax this so the server can reach it.
    local protect_home="true"
    if [[ "$WORKDIR" == /home/* ]]; then
        protect_home="read-only"
        log_info "WORKDIR 位于 /home 下,将 ProtectHome 设为 read-only 以允许服务器访问"
    fi

    local read_write_paths="$SERVER_HOME /var/lib/taskpps /var/log/taskpps"
    if [[ "$WORKDIR" != "$SERVER_HOME" ]]; then
        read_write_paths="$read_write_paths $WORKDIR"
    fi

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
WorkingDirectory=$SERVER_HOME/server
Environment=PYTHONPATH=$SERVER_HOME/server
Environment=PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/var/lib/taskpps
Environment=TASKPPS_CONFIG=$SERVER_HOME/taskpps.yaml
Environment=TASKPPS_WORKDIR=$WORKDIR
Environment=TASKPPS_SERVER_HOME=$SERVER_HOME

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=$protect_home
ReadWritePaths=$read_write_paths
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

# Generate server config
generate_config() {
    local server_config="$SERVER_HOME/taskpps.yaml"

    if [[ ! -f "$server_config" ]]; then
        log_step "Generating server configuration..."

        local api_key
        api_key=$(openssl rand -hex 32)

        cat > "$server_config" << EOF
# TaskPPS Server Configuration
# Generated on $(date -Iseconds)

locale: zh
workdir: $WORKDIR

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

        chown taskpps:taskpps "$server_config"
        chmod 640 "$server_config"

        log_info "Server config created at $server_config"
        log_warn "IMPORTANT: API Key generated: $api_key"
        log_warn "Please save this key or update the config file"
    else
        log_info "Server config file already exists, skipping"
    fi

    # Generate project config in workdir (always, regardless of WORKDIR vs SERVER_HOME)
    local project_config="$WORKDIR/.taskpps/taskpps.yaml"
    if [[ ! -f "$project_config" ]]; then
        log_step "Generating project configuration in workdir..."

        cat > "$project_config" << EOF
# TaskPPS 项目配置文件
# Generated on $(date -Iseconds)

locale: zh
workdir: $WORKDIR

server:
  host: 127.0.0.1
  port: 26521

executor:
  default_timeout: 3600
  max_workers: 10
  shell: /bin/bash

env: {}

plugins:
  paths: ["plugins"]

triggers: []
EOF

        chown taskpps:taskpps "$project_config"
        chmod 640 "$project_config"
        log_info "Project config created at $project_config"
    fi
}

# Generate /etc/profile.d/taskpps.sh
generate_profile_d() {
    local profile_file="/etc/profile.d/taskpps.sh"
    log_step "Generating $profile_file..."

    cat > "$profile_file" << EOF
# TaskPPS 环境配置
# 由 deploy.sh 自动生成于 $(date -Iseconds)

export TASKPPS_WORKDIR=$WORKDIR

if [ -d "$SERVER_HOME/cli/bin" ]; then
    export PATH="$SERVER_HOME/cli/bin:\$PATH"
fi
EOF

    chmod 644 "$profile_file"
    log_info "Environment config created at $profile_file"
}

# Install ppsctl globally
install_ppsctl() {
    log_step "Installing ppsctl globally..."

    if [[ -f "$SERVER_HOME/cli/ppsctl" ]]; then
        cp "$SERVER_HOME/cli/ppsctl" /usr/local/bin/ppsctl
        chmod 755 /usr/local/bin/ppsctl
        log_info "ppsctl installed to /usr/local/bin/ppsctl"
    elif [[ -f "$SERVER_HOME/cli/bin/ppsctl" ]]; then
        cp "$SERVER_HOME/cli/bin/ppsctl" /usr/local/bin/ppsctl
        chmod 755 /usr/local/bin/ppsctl
        log_info "ppsctl installed to /usr/local/bin/ppsctl"
    else
        log_warn "ppsctl binary not found at $SERVER_HOME/cli — skipping global install"
    fi
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

    # Pre-flight check: verify the app can be imported by the taskpps user
    # (catches missing deps / import errors before systemd hides them)
    log_info "  验证应用可导入 (taskpps 用户)..."
    if su -s /bin/bash taskpps -c "
        export HOME=/var/lib/taskpps
        export TASKPPS_WORKDIR=$WORKDIR
        export TASKPPS_CONFIG=$SERVER_HOME/taskpps.yaml
        export TASKPPS_SERVER_HOME=$SERVER_HOME
        export PYTHONPATH=$SERVER_HOME/server
        cd $SERVER_HOME/server
        $VENV_DIR/bin/python -c 'import taskpps.main; print(\"OK\", taskpps.main.app.title)'
    " 2>&1; then
        log_info "  应用导入验证通过"
    else
        log_error "应用导入失败!请检查上面的错误输出"
        exit 1
    fi

    # Pre-flight check: verify taskpps user can actually read/write workdir
    log_info "  验证 workdir 读写权限..."
    if su -s /bin/bash taskpps -c "
        test -r \"$WORKDIR\" && test -w \"$WORKDIR\" && echo READWRITE_OK || echo READWRITE_FAIL
    " 2>&1 | grep -q READWRITE_OK; then
        log_info "  workdir 可读写: $WORKDIR"
    else
        log_warn "taskpps 用户无法读写 $WORKDIR — 检查父目录权限和 ProtectHome 设置"
        log_warn "  ls -ld $WORKDIR: $(ls -ld "$WORKDIR" 2>/dev/null)"
    fi

    # Pre-flight check: state.db (and other runtime files) under workdir must
    # be owned by taskpps. If a previous run created them under a different
    # user, SQLite will fail with "attempt to write a readonly database".
    # Fix it automatically rather than letting the service start in a broken state.
    if [[ -d "$WORKDIR/.taskpps" ]]; then
        local bad_owner
        bad_owner=$(find "$WORKDIR/.taskpps" -not -user taskpps -print -quit 2>/dev/null)
        if [[ -n "$bad_owner" ]]; then
            log_warn "  发现 .taskpps 下存在非 taskpps 用户的文件,自动修正所有权..."
            chown -R taskpps:taskpps "$WORKDIR/.taskpps"
            log_info "  已修正: $(ls -ld "$WORKDIR/.taskpps" 2>/dev/null)"
        fi
    fi

    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl start "$SERVICE_NAME"
    sleep 3

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "Service started successfully!"
        systemctl status "$SERVICE_NAME" --no-pager
    else
        log_error "Service failed to start!"
        log_info "--- systemd journal (last 50 lines) ---"
        journalctl -u "$SERVICE_NAME" --no-pager -n 50
        if [[ -f "/var/log/taskpps/error.log" ]]; then
            log_info "--- gunicorn error log (last 50 lines) ---"
            tail -n 50 "/var/log/taskpps/error.log" 2>/dev/null || true
        fi
        if [[ -f "$WORKDIR/.taskpps/logs/gunicorn-error.log" ]]; then
            log_info "--- workdir gunicorn log ---"
            tail -n 50 "$WORKDIR/.taskpps/logs/gunicorn-error.log" 2>/dev/null || true
        fi
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
    rm -f "/etc/profile.d/taskpps.sh"
    rm -f "/usr/local/bin/ppsctl"
    systemctl daemon-reload

    log_info "Service uninstalled"
    log_warn "Project files at $SERVER_HOME were NOT removed"
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
    select_workdir
    install_python_deps
    create_user
    setup_directories
    install_project_deps
    build_web_ui
    generate_service_file
    generate_config
    generate_profile_d
    install_ppsctl
    enable_service
    start_service

    log_info "========================================"
    log_info "Deployment completed successfully!"
    log_info "========================================"
    log_info "Server home:  $SERVER_HOME"
    log_info "Project workdir: $WORKDIR"
    log_info "Service:      systemctl status $SERVICE_NAME"
    log_info "Logs:         journalctl -u $SERVICE_NAME -f"
    log_info "Access log:   tail -f /var/log/taskpps/access.log"
    log_info "Error log:    tail -f /var/log/taskpps/error.log"
    log_info "Config:       $SERVER_HOME/taskpps.yaml"
    log_info "Project config: $WORKDIR/.taskpps/taskpps.yaml"
    log_info "Data:         /var/lib/taskpps"
    log_info "Logs dir:     /var/log/taskpps"
    log_info "ppsctl:       /usr/local/bin/ppsctl"
    log_info "Env config:   /etc/profile.d/taskpps.sh"
    log_info ""
    log_info "Shared workdir (world-writable):"
    log_info "  $WORKDIR is mode 2777 (rwxrwxrwx + setgid)."
    log_info "  Any logged-in user can create / edit / remove files here — no per-user setup."
    log_info "  Note: new files default to 0644 (only the creator can write them)."
    log_info "  To let everyone edit a specific file: chmod 666 <file>"
    log_info "  To let everyone edit every new file:  umask 000  (in your shell rc)"
    log_info ""
    log_info "Endpoints:"
    log_info "  API:       http://$(hostname -I | awk '{print $1}'):26521/api"
    log_info "  Web UI:    http://$(hostname -I | awk '{print $1}'):26521/"
    log_info "  Agent WS:  ws://$(hostname -I | awk '{print $1}'):26521/api/ws/agent"
    log_info "  Health:    http://$(hostname -I | awk '{print $1}'):26521/api/health"
}

# Parse --workdir argument
parse_workdir_arg() {
    local args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --workdir)
                if [[ -z "${2:-}" ]]; then
                    log_error "--workdir requires a path argument"
                    exit 1
                fi
                WORKDIR="$2"
                shift 2
                ;;
            --workdir=*)
                WORKDIR="${1#*=}"
                shift
                ;;
            *)
                args+=("$1")
                shift
                ;;
        esac
    done
    set -- "${args[@]}"
    echo "${1:-install}"
}

# Main
CMD=$(parse_workdir_arg "$@")
case "$CMD" in
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
        echo "Usage: $0 [install|uninstall|status|restart|logs|stop|start] [--workdir <path>]"
        echo ""
        echo "Commands:"
        echo "  install    - Full installation with systemd (default)"
        echo "  uninstall  - Remove systemd service and ppsctl"
        echo "  status     - Show service status"
        echo "  restart    - Restart the service"
        echo "  logs       - Follow service logs"
        echo "  stop       - Stop the service"
        echo "  start      - Start the service"
        echo ""
        echo "Options:"
        echo "  --workdir <path>  - Project workdir for pipelines/agents/credentials"
        echo "                      (default: /opt/taskpps, non-interactive mode)"
        exit 1
        ;;
esac