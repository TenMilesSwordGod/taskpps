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

    # 重建 execution_agent / ppsctl(走 _lib_build.sh 公共逻辑,与 deploy.sh 对齐)
    # update.sh 不强制 go:首次部署可能是 download 模式,容许不重建二进制。
    if command -v go >/dev/null 2>&1; then
        build_execution_agent
        build_ppsctl
    else
        log_warn "未检测到 'go' 命令,跳过二进制重建 (现有 /usr/local/bin/ppsctl 与 execution_agent/build/ 保持不变)"
        log_warn "如需重建,请安装 go 1.21+ 后重新运行 update.sh"
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

build_web_ui() {
    log_step "Building Web UI..."

    local web_dir="$SERVER_HOME/web"

    if [[ ! -f "$web_dir/package.json" ]]; then
        log_warn "Web UI source not found at $web_dir, skipping build"
        return
    fi

    if ! command -v node &>/dev/null; then
        log_warn "Node.js not found, skipping Web UI build"
        return
    fi

    cd "$web_dir"

    # 配置 npm 中国镜像
    npm config set registry https://registry.npmmirror.com

    npm install --prefer-offline 2>&1 | tail -5
    npm run build 2>&1 | tail -10

    if [[ -d "$web_dir/dist" ]]; then
        chown -R taskpps:taskpps "$web_dir/dist"
        log_info "Web UI built successfully → $web_dir/dist"
    else
        log_error "Web UI build failed — dist/ not found"
    fi

    rm -rf "$web_dir/node_modules"
    log_info "Cleaned up node_modules"
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
    build_web_ui
    restart_service

    log_info "========================================"
    log_info "Update completed successfully!"
    log_info "========================================"
    # update.sh 总是走本地构建路径(build),告诉用户 build result 落点
    print_install_paths "build"
}

main