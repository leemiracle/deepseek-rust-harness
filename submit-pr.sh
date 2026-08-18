#!/usr/bin/env bash
# submit-pr.sh — x-kernel PR 投递（SSH 版：push 用 SSH key，建 PR 用 gitee 返回的直达链接）
#
# 认证分层事实：
#   git push over SSH  → 用本机 SSH key（已验证 leemiracle 可用）
#   gitee API（自动建 PR/issue）→ 只认 access_token，SSH key 无效（平台设计，GitHub 同理）
# 故本脚本策略：SSH push → 打印 gitee 返回的 "Create a pull request" 直达链接 → 浏览器一键建 PR
#
# 前置（一次性，无脚本可代劳）：
#   1. 网页登录 gitee → 打开 https://gitee.com/openkylin/x-kernel/fork → 点 Fork
#   2. 之后本脚本可反复使用
#
# 用法:
#   bash submit-pr.sh            # 推两个独立 PR 分支（kerrno / fmt 还债）
#   GITEE_TOKEN=xxx bash submit-pr.sh   #（可选）有 token 时自动建 PR，连网页都不用点
set -eu
KD="/data/usershare/ai/x-kernel"
GITEE_USER="${GITEE_USER:-leemiracle}"
FORK_SSH="git@gitee.com:$GITEE_USER/x-kernel.git"
API="https://gitee.com/api/v5/repos/openkylin/x-kernel/pulls"
UPSTREAM="openkylin/x-kernel"

# fork 存在性检查（SSH 层）
if ! git ls-remote "$FORK_SSH" HEAD >/dev/null 2>&1; then
  echo "[pr] fork 不存在：请先打开 https://gitee.com/$UPSTREAM/fork 点一次 Fork（一次性）"
  exit 2
fi

cd "$KD"
git remote remove myfork 2>/dev/null || true
git remote add myfork "$FORK_SSH"

declare -A BRANCHES=(
  [feat/kerrno-key-expired]=a1f3f23
  [style/fmt-pinned-nightly]=808a9fd
)
declare -A TITLES=(
  [feat/kerrno-key-expired]="feat(kerrno): add KErrorKind::KeyExpired mapped to LinuxError::EKEYEXPIRED"
  [style/fmt-pinned-nightly]="style: cargo fmt with pinned nightly-2026-03-08 (repay 46-file fmt debt)"
)

for BR in "${!BRANCHES[@]}"; do
  SHA="${BRANCHES[$BR]}"
  TITLE="${TITLES[$BR]}"
  echo "[pr] push $SHA → $BR"
  OUT=$(git push myfork "$SHA":refs/heads/"$BR" --force 2>&1) || { echo "$OUT"; exit 1; }
  # gitee push 输出含创建 PR 直达链接（remote: Create a pull request ...）
  URL=$(echo "$OUT" | grep -oE 'https://gitee\.com/[^\s]+/pulls/[^\s]+' | head -1)
  if [ -z "$URL" ]; then
    # 兜底：gitee 手动建 PR 的表单页
    URL="https://gitee.com/$UPSTREAM/pull/new/$GITEE_USER:x-kernel:$BR...openkylin:x-kernel:main"
  fi
  if [ -n "${GITEE_TOKEN:-}" ]; then
    BODY=$(curl -s -X POST "$API" -d "access_token=$GITEE_TOKEN" \
      -d "title=$TITLE" -d "head=$GITEE_USER:$BR" -d "base=main" \
      --data-urlencode "body=见 commit message；验证证据：L1/L2/L3 exit 0 + graph 三查 PASS（agent-driven harness 实测）")
    echo "[pr] $TITLE → $(echo "$BODY" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("html_url","ERR"))')"
  else
    echo "[pr] $TITLE"
  fi
  echo "     建PR直达: $URL"
done
echo "[pr] done。无 token 模式：点上面的链接，标题建议已打印，确认后 Submit。"
