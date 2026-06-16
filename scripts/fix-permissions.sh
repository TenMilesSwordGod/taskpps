#!/usr/bin/env bash
# fix-permissions.sh
# 修复 taskpps 项目中 nobody 拥有的文件，让 vncuser 可写
# 用法：在项目根目录执行 ./scripts/fix-permissions.sh
# 需要 sudo 权限（会提示输入密码）

set -euo pipefail

# 项目根目录（脚本所在位置的父目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

# 需要跳过的目录（缓存、依赖、构建产物）
SKIP_DIRS=(
  -name node_modules
  -o -name .git
  -o -name dist
  -o -name build
  -o -name .venv
  -o -name venv
  -o -name __pycache__
  -o -name target
  -o -name .ruff_cache
  -o -name .mypy_cache
  -o -name .pytest_cache
  -o -name .next
  -o -name .nuxt
  -o -name .vite
  -o -name .cache
  -o -name .tox
)

CURRENT_USER="$(whoami)"

echo "==> 当前用户: ${CURRENT_USER}"
echo "==> 项目根目录: ${PROJECT_ROOT}"
echo

# 收集需要修复的文件（不属于当前用户的常规文件）
# 注意：find 表达式中直接用 "${SKIP_DIRS[@]}" 展开，
# 不能用 printf "%s" 拼接（printf "%s" 只接受一个参数，多个参数会重复格式串）
echo "==> 扫描非 ${CURRENT_USER} 拥有的文件 ..."
NEED_FIX=$(find . \
  -type d \( "${SKIP_DIRS[@]}" \) -prune -o \
  -type f -print 2>/dev/null \
  | xargs -I {} stat -c '%U:%G %a %n' {} 2>/dev/null \
  | awk -v user="${CURRENT_USER}" '$1 !~ "^"user":" {print}' \
  || true)

# 同时把目录也扫一遍（新建文件需要目录可写）
NEED_FIX_DIRS=$(find . \
  -type d \( "${SKIP_DIRS[@]}" \) -prune -o \
  -type d -print 2>/dev/null \
  | xargs -I {} stat -c '%U:%G %a %n' {} 2>/dev/null \
  | awk -v user="${CURRENT_USER}" '$1 !~ "^"user":" {print}' \
  || true)

FILE_COUNT=$(echo -n "${NEED_FIX}" | grep -c . || true)
DIR_COUNT=$(echo -n "${NEED_FIX_DIRS}" | grep -c . || true)

if [[ "${FILE_COUNT}" -eq 0 && "${DIR_COUNT}" -eq 0 ]]; then
  echo "==> 无需修复，所有文件已是 ${CURRENT_USER} 拥有"
  exit 0
fi

echo "==> 发现 ${FILE_COUNT} 个文件、${DIR_COUNT} 个目录需要修复"
if [[ "${FILE_COUNT}" -gt 0 ]]; then
  echo "---- 前 10 个文件样例 ----"
  echo "${NEED_FIX}" | head -10
  echo "--------------------------"
fi
echo

# 询问 sudo 密码（如果尚未缓存）
if ! sudo -n true 2>/dev/null; then
  echo "==> 需要 sudo 权限以修改文件属主/权限"
fi

# 策略：把项目里所有源文件/目录改为 vncuser:vncuser 拥有
# 关键点：不能用 chown -R 父目录，否则会下钻到 node_modules 等 skip 目录
# 正确做法：用 find 列出所有非 skip 路径，逐个 chown（不带 -R）
echo "==> 正在批量修复（此过程可能需要数秒至数十秒）..."

# 先 chown 项目根目录本身（不带 -R，避免下钻到 skip 目录）
sudo chown "${CURRENT_USER}:${CURRENT_USER}" "${PROJECT_ROOT}" 2>/dev/null || true

# 列出项目根之下所有非 skip 路径，xargs 批量 chown（不带 -R）
find "${PROJECT_ROOT}" \
  -mindepth 1 \
  -type d \( "${SKIP_DIRS[@]}" \) -prune -o \
  \( -type f -o -type d \) -print 2>/dev/null \
  | sudo xargs -d '\n' -n 200 chown "${CURRENT_USER}:${CURRENT_USER}" 2>/dev/null || true

# 调整文件/目录权限
# 注意：.sh 等可执行脚本要保留 +x 位（不能统一 chmod 644）
echo "==> 调整文件/目录权限 ..."
find "${PROJECT_ROOT}" \
  -type d \( "${SKIP_DIRS[@]}" \) -prune -o \
  -type f ! -name '*.sh' -print 2>/dev/null \
  | xargs -d '\n' -r chmod 644 2>/dev/null || true

# .sh 等脚本保持可执行（755）
find "${PROJECT_ROOT}" \
  -type d \( "${SKIP_DIRS[@]}" \) -prune -o \
  -type f -name '*.sh' -print 2>/dev/null \
  | xargs -d '\n' -r chmod 755 2>/dev/null || true

find "${PROJECT_ROOT}" \
  -type d \( "${SKIP_DIRS[@]}" \) -prune -o \
  -type d -print 2>/dev/null \
  | xargs -d '\n' -r chmod 755 2>/dev/null || true

echo "==> 完成 ✅"
echo
echo "==> 验证（应已无 nobody 拥有的文件）"
REMAIN=$(find "${PROJECT_ROOT}" \
  -type d \( "${SKIP_DIRS[@]}" \) -prune -o \
  \( -type f -o -type d \) -print 2>/dev/null \
  | xargs -I {} stat -c '%U' {} 2>/dev/null \
  | grep -c '^nobody$' || true)
echo "剩余 nobody 文件/目录数: ${REMAIN}"
