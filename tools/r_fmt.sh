#!/usr/bin/env bash
# r_fmt.sh — L1 风格验证：cargo fmt --check（kernel 版对应物：checkpatch --strict）
# Rust 特性：rustfmt 是机械格式化（无风格争议可言），比 checkpatch 更硬——
#           风格在 Rust 生态是"机器领土"，人手格式化本身就是反模式。
# 用法: r_fmt.sh [path]   缺省整个 workspace；可传单文件/子目录
# 退出码: 0=过  1=有格式漂移  2=环境缺（报装法）
set -u
NEED_HELP() {
  echo "[r_fmt] 缺 rustfmt。装法：rustup component add rustfmt"
  echo "        缺 cargo/rustc 本体：装 rustup（https://rustup.rs，勿用 curl|sh 之外的渠道）"
  exit 2
}
command -v cargo >/dev/null || NEED_HELP
cargo fmt --version >/dev/null 2>&1 || NEED_HELP

TARGET="${1:-.}"
echo "[r_fmt] L1 fmt --check on: $TARGET"
# --check 只报告不落盘；修复永远走 `cargo fmt`（写动作走 write_file 白名单）
cargo fmt --check -- "$TARGET"
rc=$?
[ $rc -ne 0 ] && {
  echo "[r_fmt] FAIL — 修复方式：cargo fmt（整crate自动格式化；禁止手调缩进凑过检）"
  echo "        格式漂移不是逐行修的，是一次性机械重排 —— 这正是 L1 比 checkpatch 硬的原因"
}
exit $rc
