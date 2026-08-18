#!/usr/bin/env bash
# r_audit.sh — L4b 供应链验证：cargo audit + cargo deny（kernel 没有的层）
# Rust 特性：kernel 无第三方依赖树；Rust 每个 crate 拉进几十上百个传递依赖，
#           攻击面从"你的代码"扩展到"整棵依赖树的已知漏洞+许可证+来源"。
#           这是 graph 层"向上盲区"（手册 02 章）在 Rust 生态最尖锐的形态：
#           单会话只看见自己的改动，看不见依赖树深处的 CVE。
# 用法: r_audit.sh
# 退出码: 0=干净  1=有漏洞/违规  2=工具缺（报装法）
set -u
command -v cargo >/dev/null || { echo "[r_audit] missing cargo"; exit 2; }

# --- workspace 锚定 ---
RP="${RUST_PROJECT:-}"
if [ -z "$RP" ]; then
  for cand in . .. ../..; do [ -f "$cand/Cargo.toml" ] && RP="$(cd "$cand" && pwd)" && break; done
fi
[ -z "$RP" ] && { echo "[r_audit] export RUST_PROJECT=/path/to/workspace"; exit 2; }
cd "$RP" || exit 2

FAIL=0

if command -v cargo-audit >/dev/null || cargo audit --version >/dev/null 2>&1; then
  echo "[r_audit] L4b: cargo audit（RustSec 漏洞库比对整棵依赖树）"
  if ! cargo audit; then
    echo "[r_audit] FAIL — 每条漏洞给出处理：升级到哪个版本 / 为何可豁免（记账）" >&2
    FAIL=1
  fi
else
  echo "[r_audit] 缺 cargo-audit。装法：cargo install cargo-audit --locked（数据库每日更新，建议 cron）"
  exit 2
fi

# cargo deny：许可证合规 / 重复依赖 / 被 ban 的 crate / 未知来源（有则查，无则降级提示）
if cargo deny --version >/dev/null 2>&1; then
  echo "[r_audit] L4b: cargo deny check（licenses / bans / sources / advisories 四域）"
  cargo deny check 2>&1 | tail -20 || FAIL=1
else
  echo "[r_audit] (可选) cargo deny 未装：cargo install cargo-deny --locked —— 许可证/ban 治理用它"
fi

[ $FAIL -eq 0 ] && echo "[r_audit] PASS"
exit $FAIL
