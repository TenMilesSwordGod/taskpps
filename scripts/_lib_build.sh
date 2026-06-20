#!/bin/bash
# scripts/_lib_build.sh
#
# TaskPPS 公共构建库 —— deploy.sh 和 update.sh 都 source 它
# 职责:ppsctl / execution-agent 二进制构建、下载、全局安装。
# 函数约定:所有函数都 set -euo pipefail 友好,失败返回非 0。
#
# 调用方需要先 export 下列变量(给出推荐默认值):
#   LIB_SRC_DIR       源码根目录(默认:本脚本上一级)
#   LIB_SERVER_HOME   安装目标根(默认:/opt/taskpps)
#   LIB_RELEASE_URL   release 资产 base URL(默认:Gitea 内部地址)
#   LIB_RELEASE_TAG   release tag(默认:从 git describe 取,失败时用 v0.0.0)
#   LIB_LOG_INFO/WARN/ERROR/STEP  颜色 log 函数(默认内置)
#   LIB_FETCH_TOOL    wget 或 curl(默认探测)

set -euo pipefail

# ============================================================================
# 默认值(调用方 export 覆盖)
# ============================================================================
: "${LIB_SRC_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
: "${LIB_SERVER_HOME:=/opt/taskpps}"
: "${LIB_RELEASE_URL:=http://10.98.72.23:8418/AM-SYS/taskpps/releases/download}"
: "${LIB_RELEASE_TAG:=}"

# 颜色
_LIB_RED='\033[0;31m'; _LIB_GREEN='\033[0;32m'
_LIB_YELLOW='\033[1;33m'; _LIB_BLUE='\033[1;34m'; _LIB_NC='\033[0m'

# 日志函数(若调用方未提供)
if ! declare -F lib_log_info >/dev/null 2>&1; then
    lib_log_info()  { echo -e "${_LIB_GREEN}[INFO]${_LIB_NC}  $1"; }
    lib_log_warn()  { echo -e "${_LIB_YELLOW}[WARN]${_LIB_NC}  $1"; }
    lib_log_error() { echo -e "${_LIB_RED}[ERROR]${_LIB_NC} $1"; }
    lib_log_step()  { echo -e "${_LIB_BLUE}[STEP]${_LIB_NC}  $1"; }
fi

# ============================================================================
# 工具函数
# ============================================================================

# 探测 wget/curl,失败时 echo 路径并返回 0;都不可用则返回 1
_detect_fetch_tool() {
    if [[ -n "${LIB_FETCH_TOOL:-}" ]]; then
        command -v "$LIB_FETCH_TOOL" >/dev/null 2>&1 || return 1
        echo "$LIB_FETCH_TOOL"
        return 0
    fi
    if command -v wget >/dev/null 2>&1; then
        echo wget
    elif command -v curl >/dev/null 2>&1; then
        echo curl
    else
        return 1
    fi
}

# 探测主机架构(linux/amd64 或 linux/arm64)
_detect_host_arch() {
    local m
    m=$(uname -m)
    case "$m" in
        x86_64)  echo amd64 ;;
        aarch64) echo arm64 ;;
        arm64)   echo arm64 ;;
        *)       lib_log_error "不支持的架构: $m(目前仅 amd64/arm64)"; return 1 ;;
    esac
}

# 探测主机 OS
_detect_host_os() {
    local o
    o=$(uname -s | tr '[:upper:]' '[:lower:]')
    case "$o" in
        linux)   echo linux ;;
        darwin)  echo darwin ;;
        *)       lib_log_error "不支持的 OS: $o(目前仅 linux/darwin)"; return 1 ;;
    esac
}

# 从 git describe 取 tag,失败回退
_resolve_release_tag() {
    if [[ -n "$LIB_RELEASE_TAG" ]]; then
        echo "$LIB_RELEASE_TAG"
        return
    fi
    if command -v git >/dev/null 2>&1 && [[ -d "$LIB_SRC_DIR/.git" ]]; then
        local t
        t=$(git -C "$LIB_SRC_DIR" describe --tags --abbrev=0 2>/dev/null || true)
        if [[ -n "$t" ]]; then
            echo "$t"
            return
        fi
    fi
    echo "v0.0.0"
}

# ============================================================================
# 公共 API
# ============================================================================

# 硬退出:go 不可用时打印安装指引并 exit 1
require_go() {
    if command -v go >/dev/null 2>&1; then
        lib_log_info "go 已安装: $(go version)"
        return 0
    fi
    cat >&2 <<EOF
${_LIB_RED}[ERROR]${_LIB_NC} 未检测到 'go' 命令,无法本地构建 ppsctl / execution-agent。

请安装 Go 1.21+ 后重新运行:
  Debian/Ubuntu : sudo apt-get update && sudo apt-get install -y golang-go
  RHEL/CentOS   : sudo yum install -y golang
  官方一键安装  : https://go.dev/dl/  (下载 go1.21+ 后 tar -C /usr/local -xz)

或者改用 release 下载模式(无需 Go):
  sudo ./scripts/deploy.sh install --binary-source=download --release-tag=vX.Y.Z
EOF
    exit 1
}

# 编译 ppsctl。结果写到 <src>/cli/bin/ppsctl,并 copy 到 /usr/local/bin/ppsctl
# 入参:$1 = ppsctl 最终安装路径(默认 /usr/local/bin/ppsctl)
build_ppsctl() {
    local install_path="${1:-/usr/local/bin/ppsctl}"
    local cli_dir="$LIB_SRC_DIR/cli"
    local out_dir="$cli_dir/bin"

    if [[ ! -f "$cli_dir/main.go" ]]; then
        lib_log_error "找不到 $cli_dir/main.go,跳过 ppsctl 构建"
        return 1
    fi

    lib_log_step "本地构建 ppsctl..."
    mkdir -p "$out_dir"
    (
        cd "$cli_dir"
        go build -ldflags="-s -w" -o "$out_dir/ppsctl" .
    )
    chmod 755 "$out_dir/ppsctl"

    # 全局安装(允许失败但 warn —— 可能在容器/非 root 场景)
    if cp "$out_dir/ppsctl" "$install_path" 2>/dev/null; then
        chmod 755 "$install_path"
        lib_log_info "ppsctl 安装到 $install_path"
    else
        lib_log_warn "无法复制 ppsctl 到 $install_path(权限不足?),二进制留在 $out_dir/ppsctl"
    fi
}

# 编译 execution_agent。对齐 update.sh:产出当前平台 + linux/amd64 + linux/arm64
# 产物落到 <src>/execution_agent/build/
build_execution_agent() {
    local agent_dir="$LIB_SRC_DIR/execution_agent"
    local build_dir="$agent_dir/build"

    if [[ ! -f "$agent_dir/main.go" ]]; then
        lib_log_error "找不到 $agent_dir/main.go,跳过 execution_agent 构建"
        return 1
    fi

    lib_log_step "本地构建 execution_agent..."
    mkdir -p "$build_dir"

    # 当前平台主产物
    (
        cd "$agent_dir"
        go build -ldflags="-s -w" -o "$build_dir/taskpps-agent" .
    )
    # 跨平台矩阵(对齐 release.yaml 与 update.sh)
    # Issue #69: 增加 arm (armv7l) 架构支持
    for arch in amd64 arm64 arm; do
        (
            cd "$agent_dir"
            if [ "$arch" = "arm" ]; then
                GOOS=linux GOARCH=arm GOARM=7 go build -ldflags="-s -w" \
                    -o "$build_dir/taskpps-agent-linux-$arch" .
            else
                GOOS=linux GOARCH="$arch" go build -ldflags="-s -w" \
                    -o "$build_dir/taskpps-agent-linux-$arch" .
            fi
        )
    done

    # 同步到 SERVER_HOME(给 agent executor runtime 用)
    mkdir -p "$LIB_SERVER_HOME/execution_agent"
    cp -r "$build_dir" "$LIB_SERVER_HOME/execution_agent/"
    cp "$build_dir/taskpps-agent" "$LIB_SERVER_HOME/execution_agent/" 2>/dev/null || true
    lib_log_info "execution_agent 产物:"
    lib_log_info "  本地: $build_dir/"
    lib_log_info "  同步: $LIB_SERVER_HOME/execution_agent/{build,taskpps-agent}"
}

# 从 release 下载预编译产物。
# 入参:$1 = binary-source 模式(download),无 tag 则自动解析
download_release_artifacts() {
    local fetch
    if ! fetch=$(_detect_fetch_tool); then
        lib_log_error "release 下载模式需要 wget 或 curl,但都不可用"
        return 1
    fi
    local tag
    tag=$(_resolve_release_tag)
    local host_os host_arch
    host_os=$(_detect_host_os)
    host_arch=$(_detect_host_arch)

    lib_log_step "从 release 下载二进制 (tag=$tag, os=$host_os, arch=$host_arch)..."

    local ppsctl_name="taskpps-${host_os}-${host_arch}"
    local agent_name="taskpps-agent-linux-${host_arch}"
    if [[ "$host_os" == "windows" ]]; then
        ppsctl_name="${ppsctl_name}.exe"
    fi

    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' RETURN

    _fetch_to() {
        local url="$1" dest="$2"
        case "$fetch" in
            wget) wget -q --show-progress -O "$dest" "$url" ;;
            curl) curl -fSL -o "$dest" "$url" ;;
        esac
    }

    local ppsctl_url="${LIB_RELEASE_URL}/${tag}/${ppsctl_name}"
    local agent_url="${LIB_RELEASE_URL}/${tag}/${agent_name}"
    lib_log_info "  ppsctl:    $ppsctl_url"
    lib_log_info "  agent:     $agent_url"

    _fetch_to "$ppsctl_url" "$tmp_dir/ppsctl" || {
        lib_log_error "下载 ppsctl 失败: $ppsctl_url"
        return 1
    }
    _fetch_to "$agent_url" "$tmp_dir/agent" || {
        lib_log_error "下载 execution_agent 失败: $agent_url"
        return 1
    }
    chmod +x "$tmp_dir/ppsctl" "$tmp_dir/agent"

    # 安装 ppsctl
    if cp "$tmp_dir/ppsctl" /usr/local/bin/ppsctl 2>/dev/null; then
        chmod 755 /usr/local/bin/ppsctl
        lib_log_info "ppsctl 安装到 /usr/local/bin/ppsctl"
    else
        lib_log_warn "无法复制到 /usr/local/bin/ppsctl,保留在 $tmp_dir/ppsctl"
    fi

    # 安装 execution_agent
    mkdir -p "$LIB_SERVER_HOME/execution_agent/build"
    cp "$tmp_dir/agent" "$LIB_SERVER_HOME/execution_agent/build/${agent_name}"
    cp "$tmp_dir/agent" "$LIB_SERVER_HOME/execution_agent/taskpps-agent"
    chmod +x "$LIB_SERVER_HOME/execution_agent/taskpps-agent" \
             "$LIB_SERVER_HOME/execution_agent/build/${agent_name}"
    lib_log_info "execution_agent 产物:"
    lib_log_info "  $LIB_SERVER_HOME/execution_agent/taskpps-agent"
    lib_log_info "  $LIB_SERVER_HOME/execution_agent/build/${agent_name}"
}

# 部署完成时打印二进制落点 + 来源,统一告诉用户去哪找 build result
# 入参:$1 = binary-source 模式( build | download )
print_install_paths() {
    local mode="${1:-build}"
    local tag=""
    if [[ "$mode" == "download" ]]; then
        tag=$(_resolve_release_tag)
    fi

    echo ""
    lib_log_step "Build results(本次安装产物的最终位置):"
    if [[ "$mode" == "download" ]]; then
        lib_log_info "  来源:           release $tag  ($LIB_RELEASE_URL)"
    else
        lib_log_info "  来源:           本地源码 (git HEAD @ $LIB_SRC_DIR)"
    fi
    lib_log_info "  ppsctl:         /usr/local/bin/ppsctl"
    lib_log_info "  execution_agent:"
    lib_log_info "    - $LIB_SERVER_HOME/execution_agent/taskpps-agent  (当前平台)"
    lib_log_info "    - $LIB_SERVER_HOME/execution_agent/build/taskpps-agent-linux-amd64"
    lib_log_info "    - $LIB_SERVER_HOME/execution_agent/build/taskpps-agent-linux-arm64"
    echo ""
}

# ============================================================================
# systemd service file 生成
# deploy.sh 和 update.sh 都共用同一份模板,避免两份脚本漂移
# ============================================================================

# 探测 $path 是否存在且 taskpps 用户可写
# 返回 0 表示可写,1 表示不可写/不存在
_path_writable_by_taskpps() {
    local path="$1"
    if [[ -z "$path" || "$path" == "/" ]]; then
        return 1
    fi
    [[ -d "$path" ]] || return 1
    # taskpps 用户存在吗?不存在(非 deploy 阶段)直接 return 0 让 system 接手
    if ! id -u taskpps >/dev/null 2>&1; then
        return 0
    fi
    # 优先用 sudo -u 真测,失败再退回到"目录存在+taskpps 用户存在即认为可写"
    if command -v sudo >/dev/null 2>&1; then
        sudo -u taskpps -n test -w "$path" 2>/dev/null && return 0
    fi
    # 兜底:root 跑 deploy 时,目录所有权正确(taskpps:taskpps)即认为可写
    local owner
    owner=$(stat -c '%U' "$path" 2>/dev/null)
    [[ "$owner" == "taskpps" ]] && return 0
    # 进一步兜底:当前进程是 root 且 taskpps 用户存在,统一信任(目录权限通常由 deploy 自己 chown)
    if [[ $EUID -eq 0 ]]; then
        return 0
    fi
    test -w "$path"
}

# 过滤掉不存在或 taskpps 不可写的路径,空格分隔
# 空字符串表示"无可写路径"——调用方应避免生成空 ReadWritePaths(会被 systemd 拒收)
_filter_writable_paths() {
    local out=""
    local p
    # 用 read 把空格分隔的输入拆分到数组,避免全局 IFS 副作用
    local -a parts
    # shellcheck disable=SC2206
    parts=( $1 )
    for p in "${parts[@]}"; do
        [[ -z "$p" ]] && continue
        if _path_writable_by_taskpps "$p"; then
            out="${out:+$out }$p"
        else
            lib_log_warn "  跳过 ReadWritePaths: $p(不存在或 taskpps 不可写)"
        fi
    done
    echo "$out"
}

# 生成 /etc/systemd/system/taskpps.service
# 调用方需要先 export:
#   LIB_SERVER_HOME  部署根(默认 /opt/taskpps)
#   LIB_VENV_DIR     venv 路径(默认 /opt/taskpps/server/.venv)
# service_name 固定 taskpps(全项目唯一)
generate_systemd_service_file() {
    local server_home="${LIB_SERVER_HOME:-/opt/taskpps}"
    local venv_dir="${LIB_VENV_DIR:-$server_home/server/.venv}"
    local service_file="/etc/systemd/system/taskpps.service"

    lib_log_step "生成 systemd service file → $service_file"

    # 防御性:过滤掉不可写的 ReadWritePaths,避免 systemd 启动失败
    local rw_paths
    rw_paths=$(_filter_writable_paths "$server_home /var/lib/taskpps /var/log/taskpps")
    if [[ -z "$rw_paths" ]]; then
        lib_log_error "没有可写路径可作为 ReadWritePaths,放弃生成 service file"
        return 1
    fi

    cat > "$service_file" <<EOF
[Unit]
Description=TaskPPS Pipeline Server (Gunicorn)
Documentation=https://github.com/liheng/taskpps
After=network.target
Wants=network.target

[Service]
Type=simple
User=taskpps
Group=taskpps
WorkingDirectory=$server_home/server
Environment=PYTHONPATH=$server_home/server
Environment=PATH=${venv_dir}/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/var/lib/taskpps
Environment=TASKPPS_CONFIG=$server_home/taskpps.yaml
Environment=TASKPPS_SERVER_HOME=$server_home

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$rw_paths
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

ExecStart=${venv_dir}/bin/gunicorn \\
    taskpps.main:app \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 0.0.0.0:26521 \\
    --workers 1 \\
    --threads 4 \\
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
    chmod 644 "$service_file"
    lib_log_info "service file 已生成: $service_file"
    systemctl daemon-reload
}

# 探测现有 service file 是否需要重写(配置漂移检测)
# 触发条件:
#   1) 不存在
#   2) 包含 TASKPPS_WORKDIR 环境变量(旧模板的残留,新模板不应再写)
#   3) ReadWritePaths 含 taskpps 不可写的路径
#   4) ExecStart 路径跟当前 server_home/venv 不一致
service_file_needs_rewrite() {
    local service_file="/etc/systemd/system/taskpps.service"
    local server_home="${LIB_SERVER_HOME:-/opt/taskpps}"
    local venv_dir="${LIB_VENV_DIR:-$server_home/server/.venv}"

    if [[ ! -f "$service_file" ]]; then
        echo "missing"
        return 0
    fi
    if grep -qE '^Environment=TASKPPS_WORKDIR=' "$service_file"; then
        echo "stale-workdir"
        return 0
    fi
    if ! grep -q "ExecStart=${venv_dir}/bin/gunicorn" "$service_file"; then
        echo "exec-mismatch"
        return 0
    fi
    # 检查 ReadWritePaths 里每个路径是否 taskpps 仍可写
    local rw_line
    rw_line=$(grep '^ReadWritePaths=' "$service_file" | head -1 | cut -d= -f2-)
    for p in $rw_line; do
        if ! _path_writable_by_taskpps "$p"; then
            echo "unwritable: $p"
            return 0
        fi
    done
    echo "ok"
    return 1
}
