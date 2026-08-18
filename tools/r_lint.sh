#!/usr/bin/env bash
# r_lint.sh — L2 语义 lint：cargo clippy --all-targets -- -D warnings
# （kernel 版对应物：sparse C=2 + coccinelle）
# Rust 特性：kernel 需要 sparse 补类型/地址空间检查，Rust 把这些做进了编译器本体，
#           clippy 补的是"惯用法"层（idiom 层：unwrap/clone/低效模式/可疑 API 用法）。
#           -D warnings = kernel "W=1 警告=失败" 心态的 Rust 等价物。
# 用法: r_lint.sh [crate-filter]   缺省 -p 整个 workspace 的每个成员
# 退出码: 0=过  1=有警告（-D 已把 warning 升级为 error）  2=环境缺
set -u
NEED_HELP() {
  echo "[r_lint] 缺 clippy。装法：rustup component add clippy"
  exit 2
}
command -v cargo >/dev/null || { echo "[r_lint] missing cargo（装 rustup）"; exit 2; }
cargo clippy --version >/dev/null 2>&1 || NEED_HELP

# 治理红线（goodhart_guards.py 也会在 diff 层查）：这里拦命令行级绕过
if echo "$*" | grep -qE '\-\-cap-lints|RUSTFLAGS=.*-A\s*warnings|-A\s+clippy'; then
  echo "[r_lint] 拒绝：命令行压制警告（--cap-lints / RUSTFLAGS -A）= Goodhart 通道（手册 02 章）" >&2
  exit 1
fi

cd "$(cargo locate-project --workspace 2>/dev/null | sed 's/.*: "//;s/"$//' | xargs dirname 2>/dev/null || .)" 2>/dev/null || cd .

echo "[r_lint] L2 clippy -D warnings（all-targets: 含 tests/benches/examples —— 测试代码同样不许烂）"
if [ -n "${1:-}" ]; then
  cargo clippy --all-targets -p "$1 --" -D warnings
else
  cargo clippy --workspace --all-targets -- -D warnings
fi
rc=$?
[ $rc -ne 0 ] && echo "[r_lint] FAIL — 修第一条 warning 再重跑（报错即导航）。单条豁免须走 diff review，不许 #[allow] 充数" >&2
exit $rc
