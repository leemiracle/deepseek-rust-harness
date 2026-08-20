# Rust 文档地图 · 按问题查（不是按书查）

> 用途：AGENTS.md「去哪查」表的展开版。**按你在面对的问题类型索引**，一行给到权威源。
> 原则（手册 04 章）：只放"哪本书的哪章管什么问题"，不抄内容。

## 问题 → 文档索引

| 你面对的问题 | 权威源（书→章） | 备注 |
|---|---|---|
| 借用/生命周期报错读不懂 | The Book ch4（Understanding Ownership）+ ch10.3（Lifetime Syntax）| 报错三段式：借用在哪/为何活着/哪步冲突 |
| unsafe 怎么写才 sound | **The Rustonomicon**（全本薄，必读）+ The Reference §Unsafe Code Guidelines（草案但最权威）| 每种 unsafe 原语的 invariant 逐条列 |
| FFI 边界（含内核 C ABI）| Rustonomicon ch1.3（Interoperability）+ `std::ffi` 文档 | 与 kernel-harness 的 k_lockup 同问题域 |
| Miri 测不了什么 | Miri README（GitHub rust-lang/miri）"Unsupported operations" 节 | FFI/inline asm/syscall 不支持——豁免须记账（对应 r_miri.sh 设计） |
| 错误处理选型 | The Book ch9 + `std::error` 文档 + anyhow/thiserror README | 库 vs 应用的分界线 |
| API 设计（pub 即合同）| **Rust API Guidelines**（rust-lang.github.io/api-guidelines）| 命名/灵活性/文档三 checklist，C- 前缀条款 |
| crate 文档注释 | The Book ch14.2 + Guidelines C-DOC | `///` 惯例 + missing_docs lint |
| Cargo 依赖/feature 语义 | **The Cargo Book**（doc.rust-lang.org/cargo）：Spec→Dependencies/Features 章 | feature 是叠加语义不是互斥——盲区档的补验依据 |
| Semver 机器判定 | cargo-semver-checks README（crate 级 lint 目录）| 对应 r_semver.sh 的规则来源 |
| async 心智模型 | **Asynchronous Programming in Rust**（async book，rust-lang 官方）ch1-4 + tokio Tutorial "Bridging with Sync Code" | 为什么 async fn 是状态机；spawn_blocking 边界 |
| 原子操作/内存序 | `std::sync::atomic` 模块文档（比书权威）+ nomicon ch"Data Races and Race Conditions" | Ordering 语义表直接抄模块文档 |
| no_std / embedded | **The Embedded Rust Book**（docs.rust-embassy 之外的 rust-embedded 官方）| alloc 可用性/临界区/静态分配三件套——x-kernel 同域 |
| Pin / 自引用结构 | The Book? 不够——用 `std::pin` 模块文档 + Pinning方法论（rust-lang 博客）| 写 unsafe 队列/迭代器必经 |
| trait 设计（对象安全/泛型）| The Book ch17-18 + Reference §Traits | dyn Trait 边界 & vtable 代价 |
| clippy lint 分级 | rust-lang/rust-clippy 仓库 `clippy_lints` 目录 + docs.rs/clippy | correctness>suspicious>style>pedantic——G 规则的依据 |
| 宏（声明式/过程宏）| The Book ch19 + The Little Book of Rust Macros（danielkeep）| 过程宏只在必要时 |

## 版本锚点（防文档漂移）

- 工具链以 `rust-toolchain.toml` pin 为准（x-kernel 场景：1.95.0 + nightly-2026-03-08 fmt）
- Edition 差异（2021→2024）看 The Book Appendix E 的 changelog——迁移前必读

## 消费纪律

1. 先 grep workspace 现有用法（>3 处才算惯例）再看文档——本地惯例优先于一般原则
2. 文档结论落进代码时，把来源写进 commit message 或 design.md（证据链）
