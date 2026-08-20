# deepseek-rust-harness

> DeepSeek 引擎 + 六组件骨架 + **Rust 领域插件**。`deepseek-kernel-harness` 的姊妹项目：
> 同一宿主骨架（harness工程手册 12 章）、同一引擎方言层（`engines/` 完全复用），
> 换上 Rust 验证金字塔与 graph 三病治理——**换领域 = 换 tools/ + governance/ + AGENTS.md，宿主与引擎层零改动**（插件化架构的活案例）。

## 一图看懂：kernel → rust 插件映射

核心洞察：**kernel 金字塔重心在运行时（启动冒烟），Rust 把检查前置到编译期（borrow checker），
并新增了 kernel 不存在的攻击面（crates.io 供应链）——所以金字塔变形而非平移**。

| 层 | kernel | rust | 为什么变形 |
|---|---|---|---|
| L1 风格 | checkpatch --strict | `cargo fmt --check` | rustfmt 是机械格式化，风格在 Rust 是"机器领土" |
| L2 语义 | sparse + coccinelle | `cargo clippy --all-targets -- -D warnings` | kernel 需外挂工具补类型检查；Rust 编译器本体已做，clippy 补惯用法层 |
| L3 构建 | make W=1 + 外置 objtree + **flock** | `cargo build --workspace --all-targets` + `cargo test` | cargo **自带 target/ 构建锁**（kernel 要 flock 治的互踩，工具链内建了）；测试是 Rust 一等公民，kernel 没有 |
| L4 运行 | virtme/qemu 冒烟启动 | `cargo +nightly miri test`（UB 硬检测）+ `cargo audit`（RustSec CVE） | 冒烟测"活到 login"；Miri 测"safe 抽象下无 UB"；依赖树是 kernel 没有的攻击面 |
| API 合同 | get_maintainer.pl（邮寄协议，人查） | `cargo semver-checks`（机器判 breaking） | pub 即 semver 合同 |
| 盲区补验 | allmodconfig（config 矩阵） | `cargo hack --each-feature`（feature 矩阵）+ `cargo update --dry-run`（依赖树） | 同构：组合爆炸空间单会话看不全 |

## governance 三病的 Rust 特化（手册 02 章 #65-66）

| 病 | kernel 形态 | rust 形态 |
|---|---|---|
| Goodhart | 删代码消警告 / `#if 0` / checkpatch ignore | **语言级原语**：`#[allow]` / `#[cfg(not(test))]` / 无 SAFETY 的 unsafe / `.unwrap()` 密度 / `#[ignore]` 删测试（G3-G8，比 kernel 多 3 条） |
| 向上盲区 | include/ 头文件 / Kconfig 矩阵 | **Cargo.toml 依赖树 / pub API 面 / feature 矩阵 / unsafe 边界**（路径规则 + diff 内容信号双档——pub 变动藏进行内容里，路径看不出来） |
| 冲突 | 文件→series 互踩 / objtree 互踩（flock 治） | 文件互踩同构；**Cargo.toml/Cargo.lock 是全局共享热点文件**；构建端互踩 cargo 内建锁已治 |

## 结构

```
rust_host.py          宿主：六组件骨架（E/T/C/S/L/V）+ cascade，Rust 特化工具表
engines/dialects.py   引擎方言注册表（8 引擎，与 kernel 版完全复用）
engine_probe.py       引擎冒烟探针
plugin.json           插件清单（挂点声明）
AGENTS.md             Rust 契约（unsafe/Result/borrow/Send-Sync 红线）
tools/r_fmt.sh        L1  cargo fmt --check
tools/r_lint.sh       L2  clippy --all-targets -- -D warnings
tools/r_build.sh      L3  build --workspace --all-targets + test
tools/r_miri.sh       L4a Miri UB 检测（unsafe 变动必跑）
tools/r_audit.sh      L4b cargo audit 供应链
tools/r_semver.sh     附加 semver-checks API 合同
governance/goodhart_guards.py   反 Goodhart（8 规则，Rust gaming 原语）
governance/global_conflicts.py  盲区（路径档 + diff 内容信号档）
governance/patch_queue.py       冲突（Cargo.toml/lock 热点警告）
hooks/authorize.py    fail-closed 权限门（cargo publish 不可撤回 / RUSTFLAGS=-A 通道）
state/                progress.md（断点续传）+ patch_ledger.jsonl（共享账本）
```

## 快速开始

```bash
python3 rust_host.py --self-test          # 零依赖自检（不需 key/rust 工具链）
python3 hooks/authorize.py                # L 组件断言组
python3 governance/goodhart_guards.py --self-test   # 三件套各自可测

export KH_API_KEY=...                     # 或 DEEPSEEK_API_KEY
export RUST_PROJECT=/path/to/workspace    # 不设则自动探测 Cargo.toml
python3 rust_host.py --task "给 src/parser.rs 的 parse() 补错误处理并过 L1-L3"
```

换引擎只动 env（手册 09 章方言注册表）：`KH_BASE_URL`/`KH_ENGINE`/`KH_LOOP_MODEL`，
8 引擎矩阵与四针脚接线详见 `INTEGRATION.md`。

## 与 kernel 版的关系

- `engines/` + 宿主骨架：**零改动复用**（这是插件化的结构证明）
- `tools/`：金字塔**变形重写**（重心上移 + 供应链新层）
- `governance/`：三病框架同构，规则**按 Rust 语言特性重实例化**
- `hooks/`：黑名单重实例化（publish 不可撤回 > push -f；RUSTFLAGS=-A 是 kernel 不存在的 Goodhart 通道）

## 📄 License

[MIT](LICENSE) © 2026 leemiracle

## 2026-08-20 扩充：knowledge/ 最佳实践层

```
knowledge/
├── rust_docs_map.md     按问题查的文档地图（19 类问题→权威源；本地惯例优先原则）
└── rust_practices.md    12 张语义级实践卡（SAFETY 三要素/unwrap 豁免边界/feature 叠加陷阱/
                         async 隐蔽阻塞/drop 顺序/no_std 堆约束…clippy 管不到、review 常漏的）
```

定位：AGENTS.md 红线是**禁令**，practices 卡是**正例**，docs_map 是**查询协议**——三层构成 Instructions 子系统的领域纵深。
