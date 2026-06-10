#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Deployment Script (pip + gunicorn)
# ============================================================================
# Usage: sudo ./scripts/deploy.sh [install|uninstall|status|restart|logs] \
#                                 [--workdir <path>] \
#                                 [--binary-source build|download] \
#                                 [--release-tag <tag>]
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="taskpps"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
VENV_DIR="/opt/taskpps/server/.venv"
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
SERVER_HOME="/opt/taskpps"
BINARY_SOURCE=""   # build | download,由 select_binary_source 填充,也可由 --binary-source 覆盖
RELEASE_TAG=""     # 仅 download 模式使用,可由 --release-tag 覆盖

# 公共构建/下载/安装库(deploy.sh 与 update.sh 共用)
# shellcheck source=./_lib_build.sh
source "$SCRIPT_DIR/_lib_build.sh"

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

# Select project workdir (deprecated — deploy.sh no longer manages project directories)
select_workdir() {
    log_warn "select_workdir() 已废弃, deploy.sh 不再管理项目目录"
    log_info "请使用 ppsctl init --register-current-folder 初始化项目"
}

# Setup project directories
setup_directories() {
    log_step "Setting up server directories..."

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
    rsync -a --delete \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.pytest_cache' \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='.taskpps' \
        --exclude='pipelines' \
        --exclude='agents' \
        --exclude='credentials' \
        --exclude='tasks' \
        --exclude='plugins' \
        "$PROJECT_ROOT/" "$SERVER_HOME/"

    chown -R taskpps:taskpps "$SERVER_HOME"

    # Create server data directory
    mkdir -p "$SERVER_HOME/.taskpps"
    chown -R taskpps:taskpps "$SERVER_HOME/.taskpps"
    chmod 750 "$SERVER_HOME/.taskpps"
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
# 实际生成逻辑在 _lib_build.sh,deploy.sh / update.sh 共享,避免模板漂移
generate_service_file() {
    export LIB_SERVER_HOME="$SERVER_HOME"
    export LIB_VENV_DIR="$VENV_DIR"
    generate_systemd_service_file
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
}

# Generate /etc/profile.d/taskpps.sh
generate_profile_d() {
    local profile_file="/etc/profile.d/taskpps.sh"
    log_step "Generating $profile_file..."

    cat > "$profile_file" << EOF
# TaskPPS 环境配置
# 由 deploy.sh 自动生成于 $(date -Iseconds)

if [ -d "$SERVER_HOME/cli/bin" ]; then
    export PATH="$SERVER_HOME/cli/bin:\$PATH"
fi
EOF

    chmod 644 "$profile_file"
    log_info "Environment config created at $profile_file"
}

# Install ppsctl and execution-agent binaries
# 来源选择(本地构建 vs release 下载)由 BINARY_SOURCE 控制:
#   1) CLI 参数 --binary-source 优先
#   2) 否则交互式询问(非交互模式默认 build)
#   3) build 模式若缺 go,require_go 会硬退出 + 打印安装指引
install_cli_and_agent_binaries() {
    log_step "安装 ppsctl 和 execution-agent 二进制..."

    # 把 deploy.sh 的 --release-tag 透传给 _lib_build.sh(它读 $LIB_RELEASE_TAG)
    if [[ -n "$RELEASE_TAG" ]]; then
        export LIB_RELEASE_TAG="$RELEASE_TAG"
    fi

    # 1. 决定 source
    if [[ -z "$BINARY_SOURCE" ]]; then
        if [[ ! -t 0 ]]; then
            # 非交互模式(例如 CI/--workdir 走过来的)默认 build
            BINARY_SOURCE="build"
            log_info "非交互模式,默认使用本地构建 (--binary-source 可覆盖)"
        else
            BINARY_SOURCE=$(select_binary_source)
        fi
    fi

    case "$BINARY_SOURCE" in
        build)
            require_go
            build_ppsctl
            build_execution_agent
            ;;
        download)
            download_release_artifacts
            ;;
        *)
            log_error "未知的 --binary-source 值: '$BINARY_SOURCE'(应为 build 或 download)"
            exit 1
            ;;
    esac

    # 2. 部署完成,统一告诉用户二进制落在哪里
    print_install_paths "$BINARY_SOURCE"
}

# 交互式选择二进制来源,结果 echo 到 stdout
select_binary_source() {
    echo "" >&2
    echo "请选择 ppsctl / execution-agent 二进制的来源:" >&2
    echo "  1) 本地源码构建 (需要 go 1.21+)" >&2
    echo "  2) 从 release 下载 (无需 go,但需联网,默认从内部 Gitea)" >&2
    echo -n "请输入选项 [1/2] (默认: 1): " >&2
    local choice
    read -r choice
    case "${choice:-1}" in
        1) echo "build" ;;
        2) echo "download" ;;
        *) echo "build" ;;
    esac
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

    # Pre-flight check: state.db under SERVER_HOME/.taskpps must
    # be owned by taskpps. If a previous run created them under a different
    # user, SQLite will fail with "attempt to write a readonly database".
    if [[ -d "$SERVER_HOME/.taskpps" ]]; then
        local bad_owner
        bad_owner=$(find "$SERVER_HOME/.taskpps" -not -user taskpps -print -quit 2>/dev/null)
        if [[ -n "$bad_owner" ]]; then
            log_warn "  发现 .taskpps 下存在非 taskpps 用户的文件,自动修正所有权..."
            chown -R taskpps:taskpps "$SERVER_HOME/.taskpps"
            log_info "  已修正: $(ls -ld "$SERVER_HOME/.taskpps" 2>/dev/null)"
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

# 独立修复 service file:不动其它部署产物,仅检测并按需重写
# /etc/systemd/system/taskpps.service。供已经在跑旧版本 service 的人
# 单独跑一次把过期的 TASKPPS_WORKDIR/不可写路径刷掉。
fix_service_file() {
    check_root
    export LIB_SERVER_HOME="$SERVER_HOME"
    export LIB_VENV_DIR="$VENV_DIR"
    local reason
    reason=$(service_file_needs_rewrite)
    if [[ "$reason" == "ok" ]]; then
        log_info "service file 无需修复 ($SERVICE_FILE)"
        return 0
    fi
    log_warn "service file 需要重写 (原因: $reason)"
    generate_systemd_service_file
    log_info "修复完成。重启服务请运行: $0 restart"
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
    build_web_ui
    generate_service_file
    generate_config
    generate_profile_d
    install_cli_and_agent_binaries
    enable_service
    start_service

    log_info "========================================"
    log_info "Deployment completed successfully!"
    log_info "========================================"
    log_info "Server home:  $SERVER_HOME"
    log_info "Service:      systemctl status $SERVICE_NAME"
    log_info "Logs:         journalctl -u $SERVICE_NAME -f"
    log_info "Access log:   tail -f /var/log/taskpps/access.log"
    log_info "Error log:    tail -f /var/log/taskpps/error.log"
    log_info "Config:       $SERVER_HOME/taskpps.yaml"
    log_info "Data:         /var/lib/taskpps"
    log_info "Logs dir:     /var/log/taskpps"
    log_info "ppsctl:       /usr/local/bin/ppsctl"
    log_info "Env config:   /etc/profile.d/taskpps.sh"
    log_info ""
    log_info "项目初始化: 请使用 ppsctl init --register-current-folder"
    log_info ""
    log_info "Endpoints:"
    log_info "  API:       http://$(hostname -I | awk '{print $1}'):26521/api"
    log_info "  Web UI:    http://$(hostname -I | awk '{print $1}'):26521/"
    log_info "  Agent WS:  ws://$(hostname -I | awk '{print $1}'):26521/api/ws/agent"
    log_info "  Health:    http://$(hostname -I | awk '{print $1}'):26521/api/health"
}

# Parse CLI args,设置全局 BINARY_SOURCE / RELEASE_TAG,并 echo 子命令
parse_args() {
    local args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --workdir)
                # --workdir 已废弃,忽略并警告
                log_warn "--workdir 已废弃, deploy.sh 不再管理项目目录"
                shift 2 2>/dev/null || shift
                ;;
            --workdir=*)
                log_warn "--workdir 已废弃, deploy.sh 不再管理项目目录"
                shift
                ;;
            --binary-source)
                if [[ -z "${2:-}" ]]; then
                    log_error "--binary-source requires a value (build|download)"
                    exit 1
                fi
                BINARY_SOURCE="$2"
                shift 2
                ;;
            --binary-source=*)
                BINARY_SOURCE="${1#*=}"
                shift
                ;;
            --release-tag)
                if [[ -z "${2:-}" ]]; then
                    log_error "--release-tag requires a value (e.g. v1.2.3)"
                    exit 1
                fi
                RELEASE_TAG="$2"
                shift 2
                ;;
            --release-tag=*)
                RELEASE_TAG="${1#*=}"
                shift
                ;;
            -h|--help)
                args+=("help")
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

# 打印帮助(单独抽出来,这样 --help 和默认 usage 都复用)
show_usage() {
    echo "Usage: $0 [install|uninstall|status|restart|logs|stop|start|fix] [options]"
    echo ""
    echo "Commands:"
    echo "  install    - Full installation with systemd (default)"
    echo "  uninstall  - Remove systemd service and ppsctl"
    echo "  status     - Show service status"
    echo "  restart    - Restart the service"
    echo "  logs       - Follow service logs"
    echo "  stop       - Stop the service"
    echo "  start      - Start the service"
    echo "  fix        - 检测并重写 /etc/systemd/system/taskpps.service"
    echo "               (用于旧版残留的 TASKPPS_WORKDIR 或不可写 ReadWritePaths)"
    echo ""
    echo "Options:"
    echo "  --binary-source <mode>    ppsctl / execution-agent 二进制来源"
    echo "                            build   = 本地 go build(需要 go 1.21+)"
    echo "                            download= 从 release 下载(默认内部 Gitea)"
    echo "                            非交互模式默认 build,交互模式会询问"
    echo "  --release-tag <tag>       download 模式使用的 release tag,例如 v1.2.3"
    echo "                            (默认: git describe --tags 自动解析)"
}

# Main
CMD=$(parse_args "$@")
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
    fix)
        fix_service_file
        ;;
    help)
        show_usage
        ;;
    *)
        show_usage
        exit 1
        ;;
esac