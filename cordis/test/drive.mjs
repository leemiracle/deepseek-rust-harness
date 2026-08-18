// drive.mjs — rust 版 keyless 回归驱动（kernel 版同模式；断言 rust-dev-contract 段）
import { writeFileSync } from 'node:fs'
import { CallId } from '@deepseek-ai/dsh-llm'

export const name = 'drive-test'
export const inject = ['tools', 'systemPrompt']

export function apply(ctx) {
  const RESULT = new URL('./result.json', import.meta.url).pathname
  writeFileSync(RESULT, JSON.stringify({ stage: 'loaded' }))
  void (async () => {
    try {
      const r = await ctx.tools.execute({
        callId: CallId('rust-regress-1'),
        name: 'graph_guard',
        arguments: { base: 'HEAD', taskType: 'add' },
        signal: new AbortController().signal,
      })
      const text = r.content.map(b => (b.type === 'text' ? b.text : '')).join('')
      const reject = text.includes('REJECT')
      const asm = await ctx.systemPrompt.assemble()
      const has = asm.sections.some(s => s.name === 'rust-dev-contract')
      writeFileSync(RESULT, JSON.stringify({
        stage: 'done', tool_pipeline: reject ? 'REJECT-seen' : 'unexpected',
        contract_section: has, guard_head: text.slice(0, 260),
      }, null, 2))
      process.exit(reject && has ? 0 : 1)
    } catch (e) {
      writeFileSync(RESULT, JSON.stringify({ stage: 'error', message: String(e && e.message) }))
      process.exit(1)
    }
  })()
}
