#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Database Migration Script
# ============================================================================
# 职责：备份 state.db → 调用 Python init_db() 应用 schema 迁移
#
# 设计原则：
#   - 自身不包含任何列名信息，永远不需要修改
#   - 所有列变更定义在 server/taskpps/db/engine.py 的 _MIGRATIONS dict
#   - 幂等：多次运行安全
#
# 使用方式：
#   1. 被 deploy.sh source（导出 run_migration 函数）
#       source "$SCRIPT_DIR/migrate.sh"
#       run_migration "$SERVER_HOME" "$VENV_DIR"
#   2. 独立运行（自动检测 SERVER_HOME 和 VENV_DIR）
#       sudo ./scripts/migrate.sh
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[1;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $1"; }

# ============================================================================
# 内部：运行 Python 迁移逻辑
# 参数：$1 = SERVER_HOME, $2 = VENV_DIR
# ============================================================================
_run_python_migration() {
    local server_home="$1"
    local venv_dir="$2"
    local db_path="$server_home/.taskpps/state.db"

    if [[ ! -f "$db_path" ]]; then
        log_info "数据库不存在（新安装），跳过迁移"
        return 0
    fi

    # 准备 Python 运行环境
    local pyscript
    pyscript=$(cat <<'PYEOF'
import asyncio
import logging
import os
import sys

# Suppress noisy log output during migration
logging.basicConfig(level=logging.WARNING)
logging.getLogger("taskpps.db").setLevel(logging.INFO)

sys.path.insert(0, os.path.join(os.environ["SERVER_HOME"], "server"))
os.environ.setdefault("TASKPPS_SERVER_HOME", os.environ["SERVER_HOME"])

from taskpps.db.engine import init_db, close_db

async def migrate():
    await init_db()
    await close_db()
    print("Migration complete")

asyncio.run(migrate())
PYEOF
    )

    log_step "Running database migration..."
    TASKPPS_CONFIG="$server_home/taskpps.yaml" \
    TASKPPS_SERVER_HOME="$server_home" \
    SERVER_HOME="$server_home" \
    "$venv_dir/bin/python" -c "$pyscript" 2>&1

    log_info "Database schema is up to date"
}

# ============================================================================
# 公共 API：供 deploy.sh source 后调用
# 参数：$1 = SERVER_HOME（默认 /opt/taskpps）
#       $2 = VENV_DIR（默认 $SERVER_HOME/server/.venv）
# ============================================================================
run_migration() {
    local server_home="${1:-/opt/taskpps}"
    local venv_dir="${2:-$server_home/server/.venv}"
    local db_path="$server_home/.taskpps/state.db"
    local backup_path="$server_home/.taskpps/state.db.bak.$(date +%Y%m%d_%H%M%S)"

    log_step "Database migration: server_home=$server_home"

    if [[ ! -f "$db_path" ]]; then
        log_info "数据库不存在（新安装），跳过迁移"
        return 0
    fi

    # 备份数据库
    cp "$db_path" "$backup_path"
    log_info "数据库已备份: $backup_path"

    _run_python_migration "$server_home" "$venv_dir"
}

# ============================================================================
# 独立运行模式
# ============================================================================
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    SERVER_HOME="${SERVER_HOME:-/opt/taskpps}"
    VENV_DIR="${VENV_DIR:-$SERVER_HOME/server/.venv}"

    echo ""
    log_info "TaskPPS Database Migration (standalone)"
    echo ""

    run_migration "$SERVER_HOME" "$VENV_DIR"

    echo ""
    log_info "Migration finished. You may now restart the service:"
    log_info "  sudo systemctl restart taskpps"
    echo ""
fi
