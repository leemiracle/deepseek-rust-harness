# 引擎矩阵与接线（与 deepseek-kernel-harness/INTEGRATION.md 同构——引擎层复用的证明）

## 四针脚接线

```
rust_host.py ──┬── engines/dialects.py     （方言注册表：按 base_url 自动识别，KH_ENGINE 显式覆盖）
               ├── hooks/authorize.py      （L 组件：fail-closed；Rust 红线在这层拦）
               ├── governance/*.py         （graph 三查：Goodhart/盲区/冲突）
               └── tools/r_*.sh            （验证金字塔 L1-L4，缺工具报装法 exit 2）
```

## 8 引擎矩阵（与 kernel 版共用同一张表，tested 标记同步维护）

| 引擎 | base_url 关键字 | loop 默认 | thinker 默认 | loop 方言 | tested |
|---|---|---|---|---|---|
| zhipu | bigmodel | glm-5.3 | glm-5.3 | `thinking:disabled`（必须，否则拖慢工具循环） | ✅ |
| deepseek | deepseek | deepseek-chat | deepseek-reasoner | 无 | ⚠ |
| dashscope | dashscope | qwen3-coder-plus | qwen3-max | `enable_thinking:false` | ⚠ |
| moonshot | moonshot | kimi-k2-0905-preview | kimi-k2-0905-preview | 无 | ⚠ |
| openai | api.openai.com | gpt-5-mini | gpt-5 | 无 | ⚠ |
| anthropic | api.anthropic.com | claude-sonnet-4-5 | claude-opus-4-5 | 无（兼容层） | ⚠ |
| gemini | generativelanguage… | gemini-2.5-flash | gemini-2.5-pro | 无 | ⚠ |
| local | localhost/127.0.0.1 | qwen3-coder:30b | qwen3-coder:30b | 无（vLLM/Ollama） | ⚠ |

换引擎 = 换 env，零代码改动：

```bash
export KH_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
export KH_API_KEY=...
python3 engine_probe.py     # 接上就探：T1 对话/T2 工具调用/T3 thinker
```

## reasoning_content 铁律（Preserved Thinking，全引擎一致）

宿主 `run()` 只 append `content + tool_calls`，`reasoning_content` 天然不回灌——
deepseek-reasoner / glm-5.3 / qwen3-thinking 的思考内容全部只留结论，协议无关。

## Rust 领域的接针差异（相对 kernel 版）

- 路径锚定 env：`KERNEL_SRC` → `RUST_PROJECT`（未设则向上探测 Cargo.toml）
- L 组件新增拦截面：`cargo publish` / `RUSTFLAGS=-A` / `--cap-lints` / `cargo install --git` / `rustup 全局态`
- V 组件金字塔：checkpatch/sparse/W=1/virtme → fmt/clippy/build+test/miri+audit（+semver）
- graph 层新增信号档：pub API / unsafe / feature cfg / macro（diff 内容级检测，kernel 版只有路径级）
