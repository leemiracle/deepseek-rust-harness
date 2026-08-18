# [style/CI] main 存在 46 文件 fmt 漂移，CI fmt 检查是否非阻塞？

## 现象

在 pinned 工具链（`nightly-2026-03-08`，即 `make fmt` 所用）下执行 `cargo fmt --check`，main 分支有 **46 个文件**存在格式漂移：

```
virt/kvmm/src（4 处）、tee/tee_kernel/src/tee（4 处）、virt/kvmm/src/arch/x86_64（3 处）、
boot/kernel_elf_parser/src（3 处）、arch/kirq/src/bottom_half（3 处）、util/klogger、
tee/tipc、task/ktask、posix/types/src/time、platforms/kplat-aarch64 … 共 46 文件
```

复现：

```bash
rustup toolchain install nightly-2026-03-08 --profile minimal -c rustfmt
cargo +nightly-2026-03-08 fmt --check   # 46 files report "Diff in ..."
```

## 疑问（比漂移本身更重要）

漂移源头疑似近期合入的 PR（!620/!634/!637/!624 一系）。如果 CI 的 fmt 检查是阻塞门，这些应该进不了 main——想确认：

1. CI 是否对 fmt 做阻塞检查？若是，是否存在时序漏洞（如 fmt job 与合入窗口竞争）？
2. 若非阻塞，是否考虑升级为阻塞门（配合 `.githooks/pre-commit` 已有的本地拦截）？

## 附带贡献

我们已在本地按项目正道（`make fmt` + `SKIP_CLIPPY=1` 逃生门）完成还债：35 文件 ±330 对称重排，`make fmt` 幂等、pre-commit 通过。**如维护者需要，可以直接提交该 PR**（commit message 已按惯例写好）。

## 环境说明

自动化验证环境（agent-driven harness，aarch64）对 clone 仓库的检查结果；工具链与 rust-toolchain.toml/Makefile 一致。
