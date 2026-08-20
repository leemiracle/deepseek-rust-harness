# Rust 最佳实践卡 · 高频问题速查（L2-L4 之间的人工审查层）

> 定位：clippy 管不到、review 又常漏的**语义级**实践。每卡格式：问题→规则→反例→怎么查。
> 配合 AGENTS.md 红线使用：红线是"禁令"，本卡是"正例"。

## 卡1 · unsafe 的 SAFETY 注释怎么写才算数

- **问题**：`// SAFETY:` 写了但等于没写（"这里是安全的"）。
- **规则**：SAFETY 必须回答三件事——**谁保证**（调用方/类型系统/锁）、**保证什么 invariant**、**何时失效**。
- 正例：`// SAFETY: caller guarantees ptr is non-null and aligned to u64; valid until the lock is released (see X).`
- **查**：`governance/goodhart_guards.py` G6 查存在性；语义质量人工审——SAFETY 缺"谁保证"的算半违规。

## 卡2 · unwrap 的豁免边界

- **问题**：270 个 unwrap 的 crate（io/kio 实测）哪些可留？
- **规则**：**可留**——测试、main 之前的启动断言、proof obligation 明确（`Mutex::new` 不可能失败）；**必删**——IO 路径、锁内、可由用户输入影响的分支。
- **查**：按路径分档统计（`grep -c "unwrap()" | sort`），IO/mm crate 零容忍，xtask 构建工具宽档。

## 卡3 · clone 是决策不是默认

- **规则**：每次 `.clone()` 能答上"克隆了什么/多大/为什么不能借"。Arc 大对象 clone 便宜≠逻辑正确（别名语义）。
- **查**：review 时对大结构（>64B/含堆）clone 问一句。

## 卡4 · 错误类型的设计

- **问题**：`Box<dyn Error>` 一把梭，调用方无法 match。
- **规则**：库 crate 用 `thiserror` 具名变体；变体粒度=调用方需要区分处理的粒度；`#[non_exhaustive]` 保演进。
- **查**：pub API 返回 `Box<dyn Error>` = 设计债标记。

## 卡5 · async 里的阻塞（含"看起来不阻塞"的）

- **规则**：async 上下文禁：std::sync::Mutex 长持、文件/网络同步 IO、`std::thread::sleep`、>100µs 的 CPU 循环。
- 隐蔽源：`reqwest::blocking`、日志的同步 sink、锁内 await（锁跨越 await 的另一类死锁）。
- **查**：`grep_tree "std::thread::sleep\|blocking::"` async 模块；锁跨 await 用 clippy `await_holding_lock`。

## 卡6 · feature 的叠加陷阱

- **问题**：feature 被当互斥开关用（`fast`/`safe` 二选一）——Cargo feature 是**叠加**的，同时开 `fast+safe` 未定义。
- **规则**：互斥语义用 cfg 的显式冲突检查（build.rs 或编译错误）；feature 名用"添加物"命名（`json`、`tls`）不用"方式"命名（`fast`）。
- **查**：`cargo hack --each-feature --feature-pairs`（对应 r_build 的盲区补验档）。

## 卡7 · Send/Sync 边界被打破时

- **问题**：`unsafe impl Send` 之后没人记得为什么安全。
- **规则**：unsafe impl 必带注释说明"哪个字段本应不 Send、为什么实际安全"；用 newtype 包裹而非裸 impl。
- **查**：`grep_tree "unsafe impl"` 逐条过。

## 卡8 · API 的最小承诺

- **规则**：参数收 `impl Into<String>` 还是 `&str`？——默认 `&str`/`&[u8]`（最小权力），确有所有权需求再放宽；返回 `impl Iterator` 优于 `Vec`（不承诺收集顺序）；能用关联类型不用泛型参数。
- 依据：API Guidelines C-ACCEPT/CTOR/RX。
- **查**：pub 签名逐条问"我承诺了多少"。

## 卡9 · 依赖是攻击面（crates.io 供应链）

- **规则**：新依赖四问——download 量/最近提交/`cargo audit` 干净/LICENSE 兼容。版本 pin 到 minor；workspace 统一 `[workspace.dependencies]`（x-kernel 已是）。
- **查**：`tools/r_audit.sh` + Cargo.toml diff 必须单独 commit（AGENTS.md 已有，此处是理由链）。

## 卡10 · 测试的确定性

- **规则**：测试禁 `sleep(race 条件掩盖)`；禁依赖迭代器顺序的 HashMap；并行测试共享资源用 `serial_test` 或独立 fixture。
- **查**：`grep_tree "thread::sleep\|Duration::from" tests/` 抽查。

## 卡11 · Drop 顺序依赖

- **问题**：字段 drop 顺序（声明序）被隐式依赖——重构挪字段 = 崩溃。
- **规则**：有顺序依赖的字段加注释 `// drop order matters: A before B`；复杂生命周期用显式 `drop(x)`。
- **查**：含锁+句柄的结构体 review 必查。

## 卡12 · no_std 语境的堆约束

- **规则**（内核场景）：全局分配器失败不能 unwrap panic——`try_reserve`/fallible 分配；静态分配优先（`static mut` 替代是 unsafe，用 `OnceLock`/`SpinLock<Option<T>>` 模式）。
- **查**：`alloc::` 调用点在禁堆路径（中断上下文）出现即违规——与 kernel-harness 的 linux_docs_map 铁律 1 同源。
