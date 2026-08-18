#!/usr/bin/env bash
# r_fmt.sh — L1 风格验证：cargo fmt --check（kernel 版对应物：checkpatch --strict）
# Rust 特性：rustfmt 是机械格式化（无风格争议可言），比 checkpatch 更硬——
#           风格在 Rust 生态是"机器领土"，人手格式化本身就是反模式。
# e2e 实证教训（x-kernel 2026-08-18）：stable fmt 与项目 pinned nightly 的风格有差，
#           stable 过检 ≠ pinned 过检；工具链错配时 L1 的 exit 0 是伪证据。
#           故本脚本先探测 pinned 工具链，错配即 exit 3（而非误导性 0/1）。
# 用法: r_fmt.sh [target]   缺省整个 workspace；文件路径或 crate 名（-p）
# 退出码: 0=过  1=有格式漂移  2=环境缺  3=工具链错配（FMT_ALLOW_FALLBACK=1 可豁免降级跑）
set -u
NEED_HELP() {
  echo "[r_fmt] 缺 rustfmt。装法：rustup component add rustfmt"
  echo "        缺 cargo/rustc 本体：装 rustup（https://rustup.rs，勿用 curl|sh 之外的渠道）"
  exit 2
}
command -v cargo >/dev/null || NEED_HELP
cargo fmt --version >/dev/null 2>&1 || NEED_HELP

# --- workspace 锚定（e2e 教训：宿主 cwd=插件目录，cargo 必须锚定 RUST_PROJECT）---
RP="${RUST_PROJECT:-}"
if [ -z "$RP" ]; then
  for cand in . .. ../..; do [ -f "$cand/Cargo.toml" ] && RP="$(cd "$cand" && pwd)" && break; done
fi
[ -z "$RP" ] && { echo "[r_fmt] export RUST_PROJECT=/path/to/workspace（或把插件放进 workspace）"; exit 2; }
cd "$RP" || exit 2

# --- pinned 工具链探测（错配 = L1 伪证据）---
# 优先序：Makefile fmt 目标的 +<toolchain> > rust-toolchain.toml channel > 默认
PINNED="$(grep -E '^\s*(fmt|format):' -A2 Makefile 2>/dev/null | grep -oE '\+[a-z0-9.-]+' | head -1 | tr -d '+')"
if [ -z "$PINNED" ] && [ -f rust-toolchain.toml ]; then
  PINNED="$(grep -E '^\s*channel' rust-toolchain.toml | grep -oE '"[^"]+"' | tr -d '"' | head -1)"
fi
if [ -n "$PINNED" ]; then
  if ! rustup toolchain list 2>/dev/null | grep -q "$PINNED"; then
    echo "[r_fmt] 工具链错配：项目 pinned '$PINNED' 未安装（本机默认 $(rustup show active-toolchain 2>/dev/null || echo '?')）。"
    echo "        stable 过检 ≠ pinned 过检 —— L1 的 exit 0 在错配下是伪证据（e2e 实证：52 文件假漂移）。"
    echo "        正途：rustup toolchain install $PINNED --profile minimal -c rustfmt"
    if [ "${FMT_ALLOW_FALLBACK:-0}" = "1" ]; then
      echo "[r_fmt] FMT_ALLOW_FALLBACK=1 —— 降级用默认工具链跑，结果仅供本地参考，不可作为完成证据记账"
    else
      echo "[r_fmt] 拒绝给出误导性结果。豁免：FMT_ALLOW_FALLBACK=1 $0（记账须注明 fallback）"
      exit 3
    fi
  else
    echo "[r_fmt] pinned 工具链 '$PINNED' 已装，用其验证"
    FMT_TOOLCHAIN="+$PINNED"
  fi
fi
FMT_TOOLCHAIN="${FMT_TOOLCHAIN:-}"

TARGET="${1:-}"
echo "[r_fmt] L1 fmt --check on: ${TARGET:-<整个 workspace>}"
# --check 只报告不落盘；修复永远走 `cargo fmt`（写动作走 write_file 白名单）
# 位置参数只接受 .rs 文件；crate 名走 -p（cargo fmt 不接受目录）
if [ -n "$TARGET" ] && [ -f "$TARGET" ]; then
  cargo $FMT_TOOLCHAIN fmt --check -- "$TARGET"
elif [ -n "$TARGET" ]; then
  cargo $FMT_TOOLCHAIN fmt --check -p "$TARGET"
else
  cargo $FMT_TOOLCHAIN fmt --check
fi
rc=$?
[ $rc -ne 0 ] && {
  echo "[r_fmt] FAIL — 修复方式：cargo fmt（整crate自动格式化；禁止手调缩进凑过检）"
  echo "        格式漂移不是逐行修的，是一次性机械重排 —— 这正是 L1 比 checkpatch 硬的原因"
}
exit $rc
