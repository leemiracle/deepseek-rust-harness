#!/usr/bin/env bash
# r_semver.sh — API 兼容验证：cargo semver-checks（kernel 版对应物：get_maintainer.pl 的"对外协议"角色）
# Rust 特性：kernel 的对外协议是 LKML 邮寄规范（人查）；Rust 的对外协议是 semver 承诺 ——
#           pub 的一切都是 API 合同，major.minor.patch 不是装饰。cargo semver-checks
#           用 lints 级规则比对两个版本的公开 API 面，机器判 breaking change。
# 用法: r_semver.sh [--baseline <git-ref>]   缺省 baseline=vORIGIN（最近 tag 或 HEAD~1）
# 退出码: 0=无破坏  1=有 breaking（须升 major 或改设计）  2=环境缺/非 git 仓库
set -u
command -v cargo >/dev/null || { echo "[r_semver] missing cargo"; exit 2; }
if ! cargo semver-checks --version >/dev/null 2>&1; then
  echo "[r_semver] 缺 cargo-semver-checks。装法：cargo install cargo-semver-checks --locked"
  exit 2
fi
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "[r_semver] 需要 git 仓库（比对基线）"; exit 2; }

BASELINE=""
if [ "${1:-}" = "--baseline" ] && [ -n "${2:-}" ]; then BASELINE="$2"; fi
if [ -z "$BASELINE" ]; then
  # 缺省：最近的版本 tag；没有 tag 则 HEAD~1（首版前没有 API 合同）
  BASELINE="$(git describe --tags --abbrev=0 2>/dev/null || echo HEAD~1)"
fi

echo "[r_semver] API 面比对: baseline=$BASELINE（pub 即合同；patch 升级不许动签名）"
if cargo semver-checks --baseline "$BASELINE"; then
  echo "[r_semver] PASS — 公开 API 面无 semver 破坏"
  exit 0
else
  echo "[r_semver] FAIL — 每条 breaking 给出去向：升 major / 加 deprecation 过渡 / 改设计避开" >&2
  exit 1
fi
