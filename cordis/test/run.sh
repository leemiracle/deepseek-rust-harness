#!/usr/bin/env bash
# run.sh — rust 版 Cordis 层一键回归（kernel 版同模式；G8 样本：删 #[test]）
# 依赖：node≥18 + npm（沙盒内自动装 loader/deps；首次约 30-60s，缓存后秒级）
# 用法: bash cordis/test/run.sh   退出码 0=回归通过；KEEP_SANDBOX=1 保留现场
set -u
REPO=$(cd "$(dirname "$0")/../.." && pwd)
cd "$REPO"

SB=$(mktemp -d /tmp/rh-cordis-test.XXXXXX)
if [ "${KEEP_SANDBOX:-0}" != "1" ]; then trap 'rm -rf "$SB"' EXIT; fi
echo "[regress] sandbox: $SB"
git init -q "$SB" && git -C "$SB" config user.email t@t && git -C "$SB" config user.name t

# 内置 gaming 样本：删掉全部 #[test]（G8 必触发 + G1 配对消除，此前实证）
cat > "$SB/lib.rs" <<'EOF'
pub fn add(a: i32, b: i32) -> i32 { a + b }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn adds_two() { assert_eq!(add(1, 2), 3); }
    #[test]
    fn adds_zero() { assert_eq!(add(0, 0), 0); }
    #[test]
    fn adds_neg() { assert_eq!(add(-1, 1), 0); }
}
EOF
printf '[package]\nname = "demo"\nversion = "0.1.0"\nedition = "2021"\n' > "$SB/Cargo.toml"
git -C "$SB" add . && git -C "$SB" commit -qm init
printf 'pub fn add(a: i32, b: i32) -> i32 { a + b }\n' > "$SB/lib.rs"

cat > "$SB/package.json" <<EOF
{ "name": "rh-regress", "private": true,
  "dependencies": {
    "@deepseek-ai/cordis": "4.0.1",
    "@deepseek-ai/cordis-plugin-loader": "^1.0.2",
    "@deepseek-ai/cordis-plugin-include": "^1.0.6",
    "@deepseek-ai/cordis-plugin-group": "^1.0.1",
    "@deepseek-ai/cordis-plugin-hmr": "^1.0.16",
    "@deepseek-ai/cordis-plugin-timer": "^1.1.3",
    "@deepseek-ai/dsh-system-prompt": "0.1.0-rc.7",
    "@deepseek-ai/dsh-tools": "0.1.0-rc.7",
    "@deepseek-ai/dsh-llm": "0.1.0-rc.7",
    "deepseek-rust-harness": "file:$REPO"
  } }
EOF
(cd "$SB" && npm install --no-audit --no-fund --silent > "$SB/npm.log" 2>&1) || { echo "沙盒 npm install 失败："; tail -5 "$SB/npm.log"; exit 2; }

cat > "$SB/cordis.yml" <<EOF
- name: '@deepseek-ai/dsh-system-prompt'
- name: '@deepseek-ai/dsh-tools'
- name: 'deepseek-rust-harness'
  config:
    rustProject: $SB
    taskType: add
- name: '$REPO/cordis/test/drive.mjs'
EOF
rm -f "$REPO/cordis/test/result.json"

echo "[regress] rust Cordis 管线：loader → tools.execute(graph_guard) → prompt 装配"
(cd "$SB" && timeout -k 3 90 node node_modules/@deepseek-ai/cordis/bin.js > "$SB/boot.log" 2>&1)
RC=$?

echo "--- result ---"
cat "$REPO/cordis/test/result.json" 2>/dev/null || { echo "(result missing)"; tail -15 "$SB/boot.log" 2>/dev/null; exit 1; }
[ $RC -eq 0 ] && echo "[regress] PASS (RC=0)" || echo "[regress] FAIL (RC=$RC)"
exit $RC
