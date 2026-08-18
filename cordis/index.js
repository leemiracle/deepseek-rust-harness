/**
 * deepseek-rust-harness · Cordis plugin entry
 *
 * kernel 版姊妹插件（v0.2.0，2026-08-18 Cordis 化；模式已被 kernel 版 keyless e2e 实证）：
 *   - AGENTS.md（Rust 契约）→ ctx.systemPrompt.section(order:110)
 *   - r_* 金字塔 + graph 三查 → ctx.tools.register(defineTool) ×9
 *   - state/patch_ledger.jsonl 保持文件账本（跨宿主可移植）
 *   - 宿主循环/方言/权限 → dsh 自身（agent-loop / llm adapter / guarded execution）
 *
 * 密钥读取隔离（手册 02 章 Scope 检查单项）：runCLI 只透传白名单 env——
 * API key/凭据类变量不进子进程；文件面由 dsh fs-sandbox 治理。
 * 纯 JavaScript、零构建（git 安装免 allowBuilds，官方 publish 文档 prepare 陷阱免疫）。
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import Schema from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'

const HERE = path.dirname(fileURLToPath(import.meta.url)) // <pkg>/cordis
const PKG = path.resolve(HERE, '..')

export const name = 'deepseek-rust-harness'
export const inject = ['tools', 'systemPrompt']

export const Config = Schema.object({
  rustProject: Schema.string().default(process.env.RUST_PROJECT ?? '').description(
    'Cargo workspace 绝对路径；空则工具报装法（fail-loud）'),
  taskType: Schema.string().default('add').description(
    '默认任务类型：add | del | cleanup | refactor——Goodhart 守卫删除率阈值适用性'),
  timeoutMs: Schema.number().default(300000).description('单个工具超时（ms）；miri/全量 test 建议调大'),
})

// ---------- 工具执行内核：spawn CLI + env 白名单（密钥隔离）+ 结果预算 ----------
const RESULT_CAP = 16_000
const SAFE_ENV_KEYS = [
  'PATH', 'HOME', 'LANG', 'LC_ALL', 'TERM', 'TMPDIR', 'USER',
  'RUST_PROJECT', 'CARGO_HOME', 'RUSTUP_HOME',           // rust 工具链
  'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY',                // 代理非密钥，cargo/git 需要
]

function runCLI(cmd, args, config) {
  const env = Object.fromEntries(
    SAFE_ENV_KEYS.filter((k) => process.env[k] !== undefined).map((k) => [k, process.env[k]]))
  if (config.rustProject) env.RUST_PROJECT = config.rustProject
  return new Promise((resolve) => {
    const p = spawn(cmd, args, { cwd: PKG, env })
    let out = '', err = ''
    const timer = setTimeout(() => p.kill('SIGKILL'), config.timeoutMs)
    p.stdout.on('data', (d) => { out += d })
    p.stderr.on('data', (d) => { err += d })
    p.on('error', (e) => { clearTimeout(timer); resolve(`exit=127\nspawn failed: ${e.message}`) })
    p.on('close', (code) => {
      clearTimeout(timer)
      let text = `exit=${code}\n${out}` + (err ? `\n[stderr]\n${err}` : '')
      if (text.length > RESULT_CAP) text = text.slice(-RESULT_CAP) + '\n[truncated, kept tail 16K — 用更窄的 target 定位]'
      resolve(text)
    })
  })
}

const sh = (name) => path.join(PKG, 'tools', name)
const py = (name) => path.join(PKG, 'governance', name)
const textOut = {
  schema: { type: 'string' },
  render: (_args, value) => [{ type: 'text', text: value }],
}
const targetParam = { type: 'string', description: '目标路径（缺省整个 workspace；可传单文件/子 crate）' }

// ---------- 工具注册表：金字塔 L1-L4 + graph 三查 + 队列 ----------
const TOOL_SPECS = [
  {
    name: 'r_fmt',
    description: 'L1 风格：cargo fmt --check。rustfmt 是机器领土——风格漂移=没过，不过不碰 L2。',
    parameters: { target: targetParam },
    run: (a, c) => runCLI('bash', [sh('r_fmt.sh'), a.target ?? ''], c),
  },
  {
    name: 'r_lint',
    description: 'L2 语义：clippy --all-targets -- -D warnings（警告=失败，对应 kernel W=1 心态）。',
    parameters: { target: targetParam },
    run: (a, c) => runCLI('bash', [sh('r_lint.sh'), a.target ?? ''], c),
  },
  {
    name: 'r_build',
    description: 'L3 构建+测试：cargo build --workspace --all-targets + cargo test（cargo 自带 target 锁，无并行互踩）。',
    parameters: { target: targetParam },
    run: (a, c) => runCLI('bash', [sh('r_build.sh'), a.target ?? ''], c),
  },
  {
    name: 'r_miri',
    description: 'L4a UB 检测：cargo +nightly miri test。unsafe 变动必跑；FFI 豁免须记账（账本即证据）。',
    parameters: { target: targetParam },
    run: (a, c) => runCLI('bash', [sh('r_miri.sh'), a.target ?? ''], c),
  },
  {
    name: 'r_audit',
    description: 'L4b 供应链：cargo audit（RustSec CVE 比对整棵依赖树——kernel 没有的攻击面）。加依赖后必跑。',
    parameters: {},
    run: (_a, c) => runCLI('bash', [sh('r_audit.sh')], c),
  },
  {
    name: 'r_semver',
    description: 'API 合同：cargo semver-checks。pub 变动必跑——breaking 由机器判，不由人判。',
    parameters: { target: targetParam },
    run: (a, c) => runCLI('bash', [sh('r_semver.sh'), a.target ?? ''], c),
  },
  {
    name: 'graph_guard',
    description: 'graph 三查①反Goodhart：diff 结构级反 gaming（Rust 8 规则：#[allow] 密度/unsafe 无 SAFETY/unwrap 密度/删 #[test]…）。改完必跑；REJECT = 禁止入队。',
    parameters: {
      base: { type: 'string', description: 'git base（默认 HEAD~1）' },
      taskType: { type: 'string', description: 'add/del/cleanup/refactor（覆盖默认）' },
    },
    run: (a, c) => runCLI('python3', [py('goodhart_guards.py'), '--base', a.base ?? 'HEAD~1',
      '--task-type', a.taskType ?? c.taskType,
      ...(c.rustProject ? ['--repo', c.rustProject] : []), '--json'], c),
  },
  {
    name: 'graph_conflict',
    description: 'graph 三查②治盲区：影响面+补验清单（Cargo.toml→依赖树重验；pub API→semver+下游 crate；feature 矩阵；unsafe 边界）。改共享文件必跑。',
    parameters: {
      base: { type: 'string', description: 'git base（默认 HEAD~1）' },
      files: { type: 'string', description: '逗号分隔文件列表（与 base 二选一）' },
    },
    run: (a, c) => runCLI('python3', [py('global_conflicts.py'),
      ...(a.files ? ['--files', a.files] : ['--base', a.base ?? 'HEAD~1',
      ...(c.rustProject ? ['--repo', c.rustProject] : [])]), '--json'], c),
  },
  {
    name: 'patch_queue',
    description: 'graph 三查③治并行冲突：账本即队列，file→series 互斥。Cargo.toml/Cargo.lock 是全局共享文件——claim 语义比 kernel 更关键。claim 前必须先过①②。',
    parameters: {
      action: { type: 'string', required: true, description: 'status | claim | release | precheck' },
      series: { type: 'string', description: 'series 标识' },
      files: { type: 'string', description: '逗号分隔文件列表（claim 用）' },
      patch: { type: 'string', description: '补丁路径（precheck 用）' },
    },
    run: (a, c) => {
      const args = [py('patch_queue.py'), a.action ?? 'status']
      if (a.action === 'claim' && a.series) args.push(a.series, ...(a.files ?? '').split(',').map(s => s.trim()).filter(Boolean))
      if (a.action === 'release' && a.series) args.push(a.series)
      if (a.action === 'precheck' && a.patch) args.push(a.patch, ...(c.rustProject ? ['--repo', c.rustProject] : []))
      return runCLI('python3', args, c)
    },
  },
]

// ---------- apply：契约段 + 9 工具 ----------
export function apply(ctx, config) {
  const contract = readFileSync(path.join(PKG, 'AGENTS.md'), 'utf8')
  ctx.systemPrompt.section({
    name: 'rust-dev-contract',
    order: 110,
    text: `# Rust Dev Contract（deepseek-rust-harness）\n${contract}`,
  })
  for (const spec of TOOL_SPECS) {
    ctx.tools.register(defineTool({
      name: spec.name,
      description: spec.description,
      parameters: spec.parameters,
      output: textOut,
      async execute(args) {
        return spec.run(args ?? {}, config)
      },
    }))
  }
  ctx.logger?.info?.(`[dsh-rust-harness] 9 tools + contract section registered (rustProject=${config.rustProject || '<env RUST_PROJECT>'})`)
}
