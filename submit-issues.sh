#!/usr/bin/env bash
# submit-issues.sh — x-kernel 问题清单一键投递 gitee issue（草稿在 issues/x-kernel/）
# 用法:
#   bash submit-issues.sh              # dry-run：只打印将要投递的标题清单
#   GITEE_TOKEN=xxx bash submit-issues.sh   # 真实投递（token: gitee → 设置 → 私人令牌）
# API: POST /repos/openkylin/x-kernel/issues（gitee API v5）
set -eu
CD="$(cd "$(dirname "$0")" && pwd)"
DRAFT_DIR="$CD/issues/x-kernel"
REPO_API="https://gitee.com/api/v5/repos/openkylin/x-kernel/issues"

[ -d "$DRAFT_DIR" ] || { echo "no draft dir: $DRAFT_DIR"; exit 2; }

# 标题取 md 首行（# 开头去掉）
title_of() { head -1 "$1" | sed 's/^#\s*//'; }

shopt -s nullglob
DRAFTS=("$DRAFT_DIR"/*.md)
echo "将投递 ${#DRAFTS[@]} 份 issue → openkylin/x-kernel："
for f in "${DRAFTS[@]}"; do echo "  - $(title_of "$f")"; done

if [ -z "${GITEE_TOKEN:-}" ]; then
  echo "dry-run（未设 GITEE_TOKEN）。真实投递：GITEE_TOKEN=xxx bash $0"
  exit 0
fi

ok=0; fail=0
for f in "${DRAFTS[@]}"; do
  title="$(title_of "$f")"
  body="$(tail -n +2 "$f")"   # 跳过标题行，正文从第 2 行起
  resp=$(curl -s -X POST "$REPO_API" \
    -d "access_token=$GITEE_TOKEN" \
    -d "repo=x-kernel" \
    --data-urlencode "title=$title" \
    --data-urlencode "body=$body")
  url=$(echo "$resp" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("html_url") or "ERR:"+str(d.get("message") or d))')
  if [[ "$url" == http* ]]; then
    echo "[ok] $title → $url"; ok=$((ok+1))
  else
    echo "[fail] $title → $url"; fail=$((fail+1))
  fi
done
echo "done: $ok ok, $fail fail"
[ $fail -eq 0 ]
