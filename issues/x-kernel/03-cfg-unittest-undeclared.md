# [DX] `cfg(unittest)` 未在 build.rs 声明：外部贡献者裸跑 clippy 必挂 unexpected_cfgs

## 现象

不经 `make clippy`/xkmake 通道、直接用外部 cargo 跑 clippy 时，多个 crate 因 `unexpected_cfgs` 编译失败：

```bash
cargo clippy -p linux_sysno --all-targets -- -D warnings
# error: unexpected `cfg` condition name: `unittest`  ×5
# error: could not compile `linux_sysno` (lib) due to 5 previous errors
```

受影响（使用 `cfg(unittest)` 但未声明的）：`api/linux_sysno`（args.rs/lib.rs/errno/mod.rs/set.rs/map.rs）、`util/macros`、`util/unittest`、`util/kerrno` 等。

## 细节线索：rustdoc 侧已做，rustc 侧没做

`.cargo/config.toml` 的 `rustdocflags` 已经带了：

```toml
"--check-cfg", "cfg(unittest)",
```

但 `[build] rustflags` 没有对应声明，build.rs 也没有 `cargo::rustc-check-cfg` 输出——所以 `make doc` 通道没问题，裸 clippy 通道挂。

## 建议（任选其一）

1. 各使用 `cfg(unittest)` 的 crate 在 `build.rs` 加：

```rust
println!("cargo::rustc-check-cfg=cfg(unittest)");
```

2. 或 workspace 级 `.cargo/config.toml` 的 `[build] rustflags` 补 `--check-cfg=cfg(unittest)`（与 rustdocflags 对齐）。

方案 1 更符合 cargo 官方推荐（声明在使用处）。修复后外部贡献者可以不依赖 xkmake 直接 `cargo clippy -p <crate>`，降低首次参与摩擦。

## 环境说明

自动化验证环境实测（rustc 1.95.0 / aarch64）；临时绕过方式 `RUSTFLAGS="--check-cfg=cfg(unittest)" cargo clippy ...` 可用，但新人不知道。
