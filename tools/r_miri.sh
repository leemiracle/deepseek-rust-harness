#!/usr/bin/env bash
# r_miri.sh — L4a 运行时验证：Miri UB 检测（kernel 版对应物：virtme/qemu 冒烟启动）
# Rust 特性：kernel 冒烟测"内核能不能活到 login"；Rust 的对应终极问题是
#           "safe 抽象层之下有没有未定义行为"。Miri 用解释器执行并拦截：
#           越界/悬垂/UAF/数据竞争(weak memory emulation)/整数溢出语义/uninit 读。
#           这是 unsafe 变动的硬验证 —— clippy 看不见 UB，Miri 看得见。
# 用法: r_miri.sh [test-filter]
# 退出码: 0=过/无 UB  1=发现 UB  2=环境缺（报装法）  3=解释器不支持的 crate（可豁免，须记账说明）
set -u
command -v cargo >/dev/null || { echo "[r_miri] missing cargo"; exit 2; }
if ! cargo +nightly miri --version >/dev/null 2>&1; then
  echo "[r_miri] 缺 nightly 工具链或 miri 组件。装法："
  echo "  rustup toolchain install nightly"
  echo "  rustup +nightly component add miri"
  exit 2
fi

# Miri 不能跑 FFI/系统调用依赖重的测试 —— 限定在单元测试宇宙
export MIRIFLAGS="${MIRIFLAGS:--Zmiri-disable-isolation}"

echo "[r_miri] L4a: cargo +nightly miri test（UB = 不可辩论的失败，没有'在我机器上没事'）"
if cargo +nightly miri test ${1:+-- "$1"}; then
  echo "[r_miri] PASS — 未检测到 UB"
  exit 0
else
  rc=$?
  if [ $rc -eq 101 ] && cargo +nightly miri test ${1:-} 2>&1 | grep -q "unsupported"; then
    echo "[r_miri] SKIP(3) — 解释器不支持此 crate（FFI/内联汇编等）。豁免必须记入 state/patch_ledger.jsonl 说明理由" >&2
    exit 3
  fi
  echo "[r_miri] FAIL — UB 报告就是导航：读 'error: Undefined Behavior' 段落与 tracking pointer 来源" >&2
  exit 1
fi
