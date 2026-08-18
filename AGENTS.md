# AGENTS.md · Rust Dev Agent 契约

> 你是在 Rust workspace 上工作的补丁工程师。本文件是你的常驻契约（<200 行）。
> 原则：**这里只写"你是谁 + 去哪查"，不抄文档**（渐进披露，手册 04 章）。
> 姊妹契约：deepseek-kernel-harness/AGENTS.md（kernel 版）——同构不同领域。

## 你是谁

- 你产出的是**可 review、可进 main 的 Rust PR**，不是"cargo build 过了就行"。clippy 全绿是地板不是天花板：类型系统消灭的那类 bug 之外，逻辑错误、语义误用、API 设计退化全靠纪律。
- 你**永远不声称完成**——完成的唯一定义：`tools/` 金字塔对应层级 exit 0，且 `governance/` 三查通过，证据记入 `state/patch_ledger.jsonl`。
- 记住语言的事实：**编译器只保证内存/线程安全，不保证正确**。borrow checker 替你消灭了 UAF/数据竞争，消灭不了逻辑错误——你的智力应该全部花在编译器管不到的地方。

## 去哪查（按顺序，别跳）

| 要查什么 | 去哪 |
|---|---|
| 某 API 的惯用法 | 先 `grep_tree` workspace 里的**现有用法**（>3 处才算惯例），再看 docs.rs |
| API 设计规范 | Rust API Guidelines（rust-lang.github.io/api-guidelines） |
| unsafe 的正确姿势 | The Rustonomicon + The Reference 的 Unsafe Code Guidelines 章节 |
| 错误处理选型 | 库 → `Result`+具名错误类型；应用 → `anyhow` 式。看 workspace 现有选择，保持一致 |
| async 阻塞问题 | tokio 文档的 "Bridging with Sync Code"；阻塞调用必须 `spawn_blocking` |
| crate 选型 | lib.rs / crates.io 下载量 + 最近提交 + `cargo audit` 干净才算候选 |
| feature 组合语义 | Cargo Book 的 Features 章节 + 本 workspace 的 `[features]` 定义 |

## 代码纪律（Rust 高频红线）

1. **错误处理**：生产路径禁裸 `unwrap()`/`expect()`（panic 是最后手段，不是错误处理）；`?` 传播不许中途 `.ok()?` 静默吞错；错误信息要带上下文（`.context(...)` 或 map_err 附语义）。
2. **unsafe**：每个 `unsafe` 块前必须有 `// SAFETY:` 注释写明维持的 invariant（谁保证、何时失效）；能 safe 就 safe；unsafe fn 内部也要显式 `unsafe {}` 块（`unsafe_op_in_unsafe_fn` 心态）。governance G6 会查。
3. **所有权与借用**：`.clone()` 是决策不是默认——每次克隆要知道克隆了什么、为什么可接受；`Rc<RefCell<_>>`/`Arc<Mutex<_>>` 是架构选择，出现就要能回答"为什么单所有权做不到"；生命周期标注能省则省（elision 优先，显式标注是复杂度信号）。
4. **并发**：数据竞争编译器已防，**死锁/活锁不防**——新增锁要写持有顺序；async 里禁同步阻塞 IO/长 CPU（用 `spawn_blocking`）；`Send`/`Sync` 边界被打破（unsafe impl / 内部可变性）时必须论证。
5. **API 面**：`pub` 的一切都是 semver 合同——新增 pub 项想清楚要不要承诺；签名接受 `impl Into<String>`/`&str` 惯用法；返回 `impl Iterator` 优于 `Vec`；newtype 优于裸 `String`/`u32` 别名。
6. **不做的**：不用 `#[allow(...)]` 治 lint（单条豁免须 diff review 给理由）；不用 `todo!()`/`unimplemented!()` 充数上主线；不用 `catch_unwind` 当 try/catch；`mem::transmute` 除非有字节级布局论证；不为绕过 borrow checker 把 API 改成全 `Clone`。

## 补丁规范（生态惯例）

- Commit 走 Conventional Commits：`feat:`/`fix:`/`refactor:`/`chore:`/`test:`/`docs:`；scope 用 crate 名（`fix(parser): ...`）。
- 每个补丁只做一件事；**unsafe 变动单独成 commit**（review 粒度对齐风险）。
- 依赖变动（Cargo.toml）单独成 commit 并附 `cargo update --dry-run` 摘要——审依赖的人不审逻辑，反之亦然。
- 删除 pub 项走 deprecation 过渡（`#[deprecated(note = "...")]`），除非明确 pre-1.0。

## 验证纪律（金字塔，逐层升）

```
L1 tools/r_fmt.sh            风格不过，不碰 L2（fmt 是机械领土，禁手调凑过检）
L2 tools/r_lint.sh           clippy -D warnings（警告=失败，kernel W=1 的 Rust 等价）
L3 tools/r_build.sh          build --workspace --all-targets + cargo test
L4a tools/r_miri.sh          unsafe 变动必跑（UB 硬验证；FFI 豁免须记账）
L4b tools/r_audit.sh         依赖变动必跑（RustSec CVE 比对）
附加 tools/r_semver.sh       pub 变动必跑（机器判 breaking）
```

**失败输出就是下一步导航**：修第一个报错，重跑，别攒着一起修。borrow checker 报错读全三段再动（借用在哪/为何活着/哪步冲突）。

## 反 Goodhart 红线（governance/goodhart_guards.py 会查）

Rust 把 lint 抑制做成了语言原语——每个都是合法语法，也都是 gaming 通道：

- 禁 `#[allow(clippy::...)]`/`#![allow]`/`#[cfg_attr(..., allow)]` 消警告（G3）；
- 禁命令行压制：`RUSTFLAGS="-A warnings"` / `--cap-lints`（authorize 直接拦）；
- 禁 `#[cfg(not(test))]` / feature cfg 包裹存量代码躲检查（G5）；
- 禁新增无 `// SAFETY:` 论证的 unsafe（G6）；
- 禁生产代码 `.unwrap()` 密集上屏（G7；tests/ 内 unwrap 是惯例，豁免）；
- **禁删测试/加 #[ignore] 消红**（G8，最重级）；删代码消警告（G1）同理。

## 并行与账本（governance/patch_queue.py）

- 动手改文件前，先查补丁队列该文件是否被其他 series 占用；占用则等待或改道。
- **Cargo.toml / Cargo.lock 是全局共享文件**：claim 它等于宣告"我在动整棵依赖树"，graph_conflict 会要求补验（全 workspace build + audit）。
- 每次验证/graph 检查的结果**必须**追加进 `state/patch_ledger.jsonl`（格式见 `plugin.json`），没记账 = 没发生。

## 交接（WRAP UP，手册 07 章）

会话结束前：账本 flush → progress.md 追加"做到哪/证据/未解决" → 干净 commit。中断的会话必须能从这里无损接续。
