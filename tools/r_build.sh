#!/usr/bin/env bash
# r_build.sh — L3 构建验证：cargo build --workspace --all-targets + cargo test
# （kernel 版对应物：make W=1 增量 + 外置 objtree + flock）
# Rust 特性①：cargo 自带 target/ 构建锁（filelock）—— kernel 需要 flock 治的"并行构建互踩"
#             在 Rust 工具链里是内建治理，本脚本不需要再 flock（graph 层冲突的执行端已由工具链解决）。
# Rust 特性②：cargo test 是一等公民 —— kernel 没有单测金字塔，Rust 有；
#             测试不过 = 没构建完（all-targets 连测试编译都算进去）。
# Rust 特性③：增量是 fingerprint 级 —— 首跑编译依赖树慢属正常，续跑秒级。
# 用法: r_build.sh [test-filter]   缺省全 workspace
# 退出码: 0=build+test 全过  1=失败  2=环境缺
set -u
command -v cargo >/dev/null || { echo "[r_build] missing cargo（装 rustup）"; exit 2; }

# --- workspace 锚定（e2e 教训：宿主 cwd=插件目录，cargo 必须锚定 RUST_PROJECT）---
RP="${RUST_PROJECT:-}"
if [ -z "$RP" ]; then
  for cand in . .. ../..; do [ -f "$cand/Cargo.toml" ] && RP="$(cd "$cand" && pwd)" && break; done
fi
[ -z "$RP" ] && { echo "[r_build] export RUST_PROJECT=/path/to/workspace（或把插件放进 workspace）"; exit 2; }
cd "$RP" || exit 2

# 外置 target 目录（可选）：与源码树隔离，便于 CI 清理与多会话隔离（对应 kernel KOUT）
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-./target}"

echo "[r_build] L3: cargo build --workspace --all-targets (CARGO_TARGET_DIR=$CARGO_TARGET_DIR, cargo 自带构建锁)"
if ! cargo build --workspace --all-targets; then
  echo "[r_build] FAIL(build) — 编译器错误就是导航：修第一个 error（borrow checker 报错读全三段：borrow 在哪/为何活着/哪步冲突）" >&2
  exit 1
fi

echo "[r_build] L3: cargo test（kernel 金字塔没有的一层；失败输出即导航）"
if cargo test --workspace ${1:+-- "$1"}; then
  echo "[r_build] PASS — build+test 全绿（warnings=失败心态由 L2 clippy -D 兜底）"
  exit 0
else
  echo "[r_build] FAIL(test) — 先看第一个 panic 的断言与回溯；测试挂了禁改断言凑绿（governance 会拦 #[ignore]）" >&2
  exit 1
fi
