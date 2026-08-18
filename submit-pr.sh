#!/usr/bin/env bash
# submit-pr.sh — x-kernel PR 一键投递（gitee：fork → push → PR）
# 用法: GITEE_TOKEN=xxx bash submit-pr.sh   （token: gitee.com → 设置 → 私人令牌，勾选 projects/projects_group）
# 产物: 浏览器打开输出中的 html_url 即为 PR 页面
set -eu

REPO_OWNER=openkylin
REPO_NAME=x-kernel
BRANCH=feat/kerrno-key-expired
TOKEN="${GITEE_TOKEN:?需要 export GITEE_TOKEN（gitee 私人令牌，勾选 projects 权限）}"
API="https://gitee.com/api/v5"
CD="$(cd "$(dirname "$0")" && pwd)"   # x-kernel 仓库根（脚本放仓库根或传 $1）
KD="${1:-$CD}"

# 1 fork（幂等：已 fork 时 gitee 返回 400，忽略）
FORK=$(curl -s -X POST "$API/repos/$REPO_OWNER/$REPO_NAME/forks" \
  -d "access_token=$TOKEN" )
FORK_FULL=$(echo "$FORK" | python3 -c 'import json,sys; print(json.load(sys.stdin)["full_name"])' 2>/dev/null) \
  || FORK_FULL="${GITEE_USER:?fork 解析失败，请 export GITEE_USER=你的gitee用户名}/$REPO_NAME"
echo "[pr] fork: $FORK_FULL"

# 2 推分支（commit 已在本地：a1f3f23）
git -C "$KD" remote remove myfork 2>/dev/null || true
git -C "$KD" remote add myfork "https://${GITEE_USER}:${TOKEN}@gitee.com/${FORK_FULL#*/..}.git" 2>/dev/null \
  || git -C "$KD" remote add myfork "https://${GITEE_USER}:${TOKEN}@gitee.com/$FORK_FULL.git"
git -C "$KD" push -u myfork HEAD:refs/heads/$BRANCH

# 3 建 PR
PR_BODY='为 kerrno 补充 key-management 错误码 EKEYEXPIRED（Linux errno 127），供后续 keyring/TEE 子系统使用。

改动（8 触点，风格完全对齐既有条目）：
- KErrorKind 新增 KeyExpired 变体（含文档注释）
- as_str() / from_code() 双向映射
- From<KErrorKind> for LinuxError / TryFrom<LinuxError> 反向映射
- kerror_consts! 常量宏
- 测试：COUNT 45→46、max_code 断言、unittest 映射表追加

验证：cargo fmt --check=0；RUSTFLAGS="--check-cfg=cfg(unittest)" cargo clippy -p kerrno --all-targets -- -D warnings=0；cargo check -p kerrno=0。无 unsafe、无依赖变动、无新增 #[allow]。'

PR=$(curl -s -X POST "$API/repos/$REPO_OWNER/$REPO_NAME/pulls" \
  -d "access_token=$TOKEN" \
  -d "title=feat(kerrno): add KErrorKind::KeyExpired mapped to LinuxError::EKEYEXPIRED" \
  --data-urlencode "body=$PR_BODY" \
  -d "head=${FORK_FULL%%:*}:$BRANCH" \
  -d "base=main")
echo "$PR" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("[pr] URL:", d.get("html_url") or d)'
