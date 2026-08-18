# [DX] pre-commit hook 在缺 pinned nightly 时报错可更指向性（附一键装法）

## 现象

`.githooks/pre-commit` 的 fmt 段调用 `make fmt`（= `cargo +nightly-2026-03-08 fmt --all`）。新贡献者没装 pinned nightly 时：

```
❌ pre-commit: 'make fmt' failed (is the pinned nightly toolchain installed?).
   bypass with: SKIP_FMT=1 git commit ...
```

设计本身是好的（强一致 + SKIP_* 逃生门都齐），但这个失败信息给了新人两条路：装工具链（正确）或 `SKIP_FMT=1`（绕过，把 fmt 债带进 commit——正是 issue #01 那 46 文件漂移的成因之一）。在自动化验证中，我们的 agent 在此 hook 上消耗了大量轮次后才自行找到正解。

## 建议（低成本）

`make fmt` 失败且检测到 pinned 工具链缺失时，把装法直接打印出来，把 SKIP_* 放到其后作为次选：

```bash
if ! cargo +nightly-2026-03-08 fmt --all; then
  if ! rustup toolchain list | grep -q nightly-2026-03-08; then
    echo "📦 缺 pinned 工具链，一条命令装好：" >&2
    echo "   rustup toolchain install nightly-2026-03-08 --profile minimal -c rustfmt" >&2
    echo "   （装完直接重试 commit 即可）" >&2
    exit 1
  fi
  echo "❌ make fmt 失败（工具链已装，请看上方 rustfmt 输出）" >&2
  echo "   应急逃生门：SKIP_FMT=1 git commit ..." >&2
  exit 1
fi
```

顺序即引导：先正道，后逃生门。

## 环境说明

自动化验证环境（agent-driven）实测：75 turns 的 commit 泥潭根因即此；hook 文件 `.githooks/pre-commit` 的 SKIP 设计与 re-stage 逻辑都值得保留。
