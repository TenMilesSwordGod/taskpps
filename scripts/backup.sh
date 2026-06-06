#!/bin/bash
set -euo pipefail

# ============================================================================
# TaskPPS Backup Script
# ============================================================================
# Usage: ./scripts/backup.sh [output_dir]
# Default output: ./backups/taskpps_backup_YYYYMMDD_HHMMSS.tar.gz
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVER_HOME="/opt/taskpps"
BACKUP_DIR="${1:-$PROJECT_ROOT/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="taskpps_backup_${TIMESTAMP}"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME.tar.gz"

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

# Create temp directory for backup
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$BACKUP_DIR"

log_step "Creating backup: $BACKUP_NAME"

# Backup database (server home)
if [[ -f "$SERVER_HOME/.taskpps/state.db" ]]; then
    log_info "Backing up database..."
    mkdir -p "$TMP_DIR/server_home/.taskpps"
    cp "$SERVER_HOME/.taskpps/state.db" "$TMP_DIR/server_home/.taskpps/"
fi

# Backup server config
if [[ -f "$SERVER_HOME/taskpps.yaml" ]]; then
    log_info "Backing up server configuration..."
    mkdir -p "$TMP_DIR/server_home"
    cp "$SERVER_HOME/taskpps.yaml" "$TMP_DIR/server_home/"
fi

# Backup logs (optional, last 7 days)
if [[ -d /var/log/taskpps ]]; then
    log_info "Backing up recent logs..."
    mkdir -p "$TMP_DIR/logs"
    find /var/log/taskpps -type f -mtime -7 -exec cp {} "$TMP_DIR/logs/" \; 2>/dev/null || true
fi

# Backup project workdir pipelines/agents/credentials
if [[ -n "${TASKPPS_WORKDIR:-}" ]] && [[ -d "$TASKPPS_WORKDIR/pipelines" ]]; then
    log_info "Backing up project workdir: $TASKPPS_WORKDIR"
    mkdir -p "$TMP_DIR/workdir"
    cp -r "$TASKPPS_WORKDIR/pipelines" "$TMP_DIR/workdir/" 2>/dev/null || true
    cp -r "$TASKPPS_WORKDIR/agents" "$TMP_DIR/workdir/" 2>/dev/null || true
    cp -r "$TASKPPS_WORKDIR/credentials" "$TMP_DIR/workdir/" 2>/dev/null || true
    if [[ -f "$TASKPPS_WORKDIR/.taskpps/taskpps.yaml" ]]; then
        mkdir -p "$TMP_DIR/workdir/.taskpps"
        cp "$TASKPPS_WORKDIR/.taskpps/taskpps.yaml" "$TMP_DIR/workdir/.taskpps/"
    fi
elif [[ -d "$SERVER_HOME/pipelines" ]]; then
    # Fallback: backup from server home
    log_info "Backing up pipelines from server home..."
    if [[ -d "$SERVER_HOME/pipelines" ]]; then
        cp -r "$SERVER_HOME/pipelines" "$TMP_DIR/"
    fi
    if [[ -d "$SERVER_HOME/credentials" ]]; then
        log_warn "Backing up credentials directory (contains sensitive data)"
        cp -r "$SERVER_HOME/credentials" "$TMP_DIR/"
    fi
fi

# Create tarball
log_step "Compressing backup..."
tar -czf "$BACKUP_PATH" -C "$TMP_DIR" .

BACKUP_SIZE=$(du -h "$BACKUP_PATH" | cut -f1)

log_info "========================================"
log_info "Backup completed!"
log_info "========================================"
log_info "File: $BACKUP_PATH"
log_info "Size: $BACKUP_SIZE"
log_info ""
log_info "To restore:"
log_info "  tar -xzf $BACKUP_PATH -C /tmp/restore"