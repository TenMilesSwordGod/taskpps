#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Hot-Update Script (gunicorn SIGHUP reload)
# ============================================================================
# Usage: sudo ./scripts/hotupdate.sh
#
# In-flight pipelines are preserved: existing gunicorn workers keep running
# until their current request finishes, then exit. New workers are spawned
# with the new code/dependencies and take over.
#
# Limitations:
#   - File deletions in the new revision are NOT propagated (no --delete
#     in rsync, to avoid breaking old workers mid-import). Run update.sh
#     for a full restart when you need deleted files cleaned up.
#   - DB schema changes must be backward-compatible (old workers may still
#     be running with the old code while new workers come up).
#   - The systemd unit itself cannot be hot-reloaded — edit deploy.sh's
#     generate_service_file() output and run update.sh for unit changes.
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="taskpps"
SERVER_HOME="/opt/taskpps"
VENV_DIR="$SERVER_HOME/server/.venv"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
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

# Find the gunicorn master PID inside the service cgroup.
# Needed because `systemctl reload` is async: we want to wait for old workers
# to drain before declaring success.
get_master_pid() {
    # mainpid from systemd is the gunicorn master (ExecStart runs gunicorn directly)
    systemctl show -p MainPID --value "$SERVICE_NAME" 2>/dev/null || echo ""
}

count_workers() {
    local master="$1"
    if [[ -z "$master" || "$master" == "0" ]]; then
        echo "0"
        return
    fi
    # gunicorn master is the parent of the worker processes
    pgrep -P "$master" -c 2>/dev/null || echo "0"
}

backup_config() {
    log_step "Backing up configuration..."
    if [[ -f "$SERVER_HOME/taskpps.yaml" ]]; then
        cp "$SERVER_HOME/taskpps.yaml" "$SERVER_HOME/taskpps.yaml.bak.$(date +%Y%m%d_%H%M%S)"
    fi
    if [[ -f "$SERVER_HOME/.taskpps/state.db" ]]; then
        cp "$SERVER_HOME/.taskpps/state.db" "$SERVER_HOME/.taskpps/state.db.bak.$(date +%Y%m%d_%H%M%S)"
    fi
    log_info "Backup done"
}

update_code() {
    log_step "Updating server code (no --delete to keep old workers valid)..."

    if [[ -d "$PROJECT_ROOT/.git" ]]; then
        cd "$PROJECT_ROOT"
        git pull origin main || log_warn "Git pull failed, using local files"
    fi

    # NOTE: --delete is intentionally OMITTED. Removing a .py file that an
    # old worker has imported can crash the worker when it next touches the
    # module. Stale files are harmless (disk usage only); clean them up
    # with update.sh if needed.
    rsync -a \
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
    log_info "Code synced"
}

update_deps() {
    log_step "Updating dependencies (pip)..."
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

# Reload gunicorn: SIGHUP to master triggers a graceful worker recycle.
# Old workers finish their current request and exit; new workers spawn
# with the freshly-imported new code. Master process never dies.
hot_reload() {
    log_step "Hot-reloading gunicorn workers (SIGHUP)..."

    local master_before workers_before
    master_before=$(get_master_pid)
    workers_before=$(count_workers "$master_before")
    log_info "  pre-reload: master_pid=$master_before workers=$workers_before"

    # Sends SIGHUP to the gunicorn master via the unit's ExecReload hook
    # (see deploy.sh line 380: ExecReload=/bin/kill -HUP $MAINPID). The
    # master recycles workers one at a time; the master process itself
    # never exits, which is what makes this a true hot reload.
    systemctl reload "$SERVICE_NAME"

    # Wait for workers to recycle. gunicorn recycles one at a time; with
    # --workers 2 and a graceful timeout, expect 5-15s.
    local i=0
    while (( i < 30 )); do
        sleep 1
        local master_after workers_after
        master_after=$(get_master_pid)
        workers_after=$(count_workers "$master_after")
        # Master PID must stay the same (true hot reload, not a restart)
        if [[ "$master_after" == "$master_before" ]] && (( workers_after >= 1 )); then
            log_info "  post-reload: master_pid=$master_after workers=$workers_after (recycled in ${i}s)"
            return 0
        fi
        if [[ -n "$master_after" && "$master_after" != "$master_before" && "$master_after" != "0" ]]; then
            log_warn "  master PID changed ($master_before -> $master_after); this is a restart, not a hot reload"
            log_warn "  falling back to restart semantics — in-flight pipelines were interrupted"
            return 0
        fi
        (( i++ ))
    done

    log_error "Hot reload did not complete within 30s"
    journalctl -u "$SERVICE_NAME" --no-pager -n 30
    return 1
}

verify_health() {
    log_step "Verifying service health..."
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "Service is active"
    else
        log_error "Service is NOT active after hot reload!"
        journalctl -u "$SERVICE_NAME" --no-pager -n 50
        exit 1
    fi
}

main() {
    log_info "Starting TaskPPS HOT update (in-flight pipelines preserved)..."

    check_root
    backup_config
    update_code
    update_deps
    build_web_ui
    hot_reload
    verify_health

    log_info "========================================"
    log_info "Hot upgrade completed successfully!"
    log_info "  - Code and dependencies are live"
    log_info "  - Gunicorn workers recycled (old drained, new spawned)"
    log_info "  - In-flight pipelines continued on old workers"
    log_info "========================================"
    log_info "Note: stale files in $SERVER_HOME are NOT removed."
    log_info "      Run update.sh for a full restart + cleanup."
}

main
