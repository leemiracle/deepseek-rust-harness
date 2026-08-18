#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""global_conflicts.py — Graph 层治理之二：治"向上盲区"（Rust 版）

手册 02 章 #65-66：局部节点（单会话 agent 只 build/test 自己改的 crate）看不见全局冲突。

Rust 盲区形态（kernel 版只按路径分类；Rust 版必须 路径规则 + diff 内容信号 双档，
因为最危险的盲区 —— pub API 面变动 —— 藏在 diff 行里，路径看不出来）：
  - 改 Cargo.toml 加了个"小依赖"，传递依赖树拉进 137 个 crate，其中一个有 CVE
  - 改 pub fn 签名，本 crate 测试全绿，下游三个 crate 编译崩（semver 破坏）
  - 改 #[cfg(feature)] 分支，默认 feature 测过，--no-default-features 组合崩
  - 新增 unsafe，safe 测试全过，Miri 下数据竞争（feature 矩阵/unsafe 是编译器看不见的组合爆炸）

治法（graph 层 = 有全 workspace 视角的规则引擎）:
  路径分类 + diff 内容信号 → 生成"影响面声明 + 必须补的重验命令"。
  宿主把 required_rechecks 逐条跑完才许入补丁队列。

用法:
  python3 global_conflicts.py --base HEAD~1 [--repo DIR]        # 路径+内容双档
  python3 global_conflicts.py --files src/lib.rs,Cargo.toml     # 仅路径档
  python3 global_conflicts.py --self-test

退出码: 0=无需补验  1=有盲区须补验  2=用法错
"""
import argparse
import json
import re
import subprocess
import sys

# ===== 路径档：文件名/前缀 → (影响面等级, 必须补的重验) =====
PATH_RULES = [
    ('Cargo.toml', {
        'level': 'DEPENDENCY-TREE',
        'why': '依赖/feature 声明影响整棵传递依赖树与所有 workspace 成员；本 crate 过 ≠ 全树过',
        'recheck': [
            'cargo update --dry-run  # 看清会拉动哪些传递依赖',
            'tools/r_build.sh  # 全 workspace build+test',
            'tools/r_audit.sh  # 依赖树 CVE 比对',
        ]}),
    ('Cargo.lock', {
        'level': 'LOCKFILE',
        'why': 'lock 漂移 = 依赖树实际版本变动（应用必须提交并解释；库通常不提交 lock）',
        'recheck': ['cargo tree --duplicates  # 看版本分裂', 'tools/r_build.sh']}),
    ('build.rs', {
        'level': 'TOOLCHAIN',
        'why': '构建脚本影响每一次构建的代码生成',
        'recheck': ['cargo clean && tools/r_build.sh  # 消除增量构建的缓存侥幸']}),
    ('rust-toolchain', {
        'level': 'TOOLCHAIN',
        'why': 'toolchain 文件锁死编译器版本，变动 = 全体重编 + lint 集合变化',
        'recheck': ['cargo clean && tools/r_build.sh && tools/r_lint.sh']}),
    ('.cargo/config', {
        'level': 'TOOLCHAIN',
        'why': 'target/rustflags/别名改动影响每次构建与所有 lint 行为',
        'recheck': ['cargo clean && tools/r_build.sh']}),
    ('benches/', {
        'level': 'BENCH-ONLY',
        'why': '基准代码，无需重验主构建（clippy 仍须过）',
        'recheck': []}),
]

# ===== 内容档：diff 行信号 → 影响面（路径档看不见的半径） =====
PUB_API_RE = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?(pub\s+)?(fn|struct|enum|trait|type|mod|const|static)\b')
PUB_MARK_RE = re.compile(r'\bpub(\([^)]*\))?\s+(fn|struct|enum|trait|type|mod|const|static)\b')
UNSAFE_RE = re.compile(r'\bunsafe\b\s*(\{|\s+fn|\s+impl|trait)')
FEATURE_RE = re.compile(r'#\s*\[cfg\((\s*all\()?\s*feature\s*=')
MACRO_RE = re.compile(r'\bmacro_rules!\s+\w+')
SERDE_RE = re.compile(r'#\s*\[derive\([^)]*(Serialize|Deserialize)')

CONTENT_RULES = [
    ('pub-api', PUB_MARK_RE, {
        'level': 'API-SURFACE',
        'why': 'pub 即合同（semver）：签名/字段变动破坏所有下游；本 crate 测试绿不算数',
        'recheck': ['tools/r_semver.sh --baseline HEAD~1  # 机器判 breaking change']}),
    ('unsafe', UNSAFE_RE, {
        'level': 'SAFETY-BOUNDARY',
        'why': 'unsafe 的契约编译器不查；safe 测试全过也 可能藏 UB',
        'recheck': ['tools/r_miri.sh  # UB 硬验证（FFI 不可解释时豁免须记账）']}),
    ('feature-cfg', FEATURE_RE, {
        'level': 'FEATURE-MATRIX',
        'why': 'feature 组合是乘法空间，单一 feature 集合证明不了（对应 kernel allmodconfig 盲区）',
        'recheck': ['cargo hack --each-feature check  # 缺则 cargo install cargo-hack --locked']}),
    ('macro', MACRO_RE, {
        'level': 'MACRO-WIDE',
        'why': '宏在调用点展开，定义处测试过 ≠ 所有调用点过',
        'recheck': ['cargo build --workspace --all-targets  # 展开全部调用点']}),
]

PUB_ENUM_CTX_RE = re.compile(r'pub\s+(\([^)]*\)\s+)?enum\b')
VARIANT_LINE_RE = re.compile(r'^\s*[A-Z][A-Za-z0-9_]*\s*(\([^)]*\))?\s*,?\s*(//.*)?$')


def classify_path(path):
    """路径 → 匹配的路径档规则（最长命中；无命中=普通模块改动）"""
    best = None
    for prefix, rule in PATH_RULES:
        base = prefix.rstrip('/')
        if (path == base or path.startswith(prefix) or path.endswith('/' + base)
                or path.split('/')[-1] == base):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, rule)
    return best


def parse_diff(diff_text):
    """→ {file: {'added': [...], 'ctx': [...]}}。ctx = hunk 上下文行（含 @@ 头），
    用于 enum-variant 规则判断"加的行是否落在 pub enum 块内"。"""
    files = {}
    cur, bucket = None, None
    for line in diff_text.splitlines():
        if line.startswith('+++ b/'):
            cur = line[6:]
            files[cur] = {'added': [], 'ctx': []}
        elif line.startswith('--- a/'):
            continue
        elif cur is not None:
            if line.startswith('+') and not line.startswith('+++'):
                files[cur]['added'].append(line[1:])
            elif line.startswith('@@'):
                files[cur]['ctx'].append(line)
            elif line.startswith(' '):
                files[cur]['ctx'].append(line[1:])
    return files


def analyze(paths, added_by_file=None):
    """paths + 可选 diff 内容 → (findings, rechecks)。added_by_file 启用内容档。"""
    findings, rechecks = [], []
    seen_levels = set()

    def add_finding(file, rule, key=None):
        lvl = rule['level']
        k = key or lvl
        if k in seen_levels and key is None:
            return  # 路径档同 level 去重
        if key is not None and k in seen_levels:
            return
        seen_levels.add(k)
        findings.append({'file': file, 'level': lvl, 'why': rule['why']})
        for rc in rule['recheck']:
            if rc not in rechecks:
                rechecks.append(rc)

    for p in paths:
        m = classify_path(p)
        if m:
            prefix, rule = m
            add_finding(p, rule)

    if added_by_file:
        for fname, payload in added_by_file.items():
            added = payload['added'] if isinstance(payload, dict) else payload
            ctx = payload.get('ctx', []) if isinstance(payload, dict) else []
            joined = '\n'.join(added)
            for key, rex, rule in CONTENT_RULES:
                if rex.search(joined):
                    add_finding(fname, rule, key=f'{key}:{fname}')
            # enum-variant：pub enum 块内加行（变体行无 pub 关键字，pub-api 规则看不见）
            # e2e 实证教训（x-kernel KeyExpired）：加变体通常 non-breaking，但改判别值/
            # 加非 exhaustive 匹配敏感字段时是 breaking —— 机器判，不人判
            if ctx and any(PUB_ENUM_CTX_RE.search(c) for c in ctx):
                variants = [a for a in added if a.strip() and VARIANT_LINE_RE.match(a)]
                if variants:
                    rule = {'level': 'API-SURFACE',
                            'why': f'pub enum 块内新增 {len(variants)} 个变体（变体行无 pub 关键字，pub-api 规则盲区）；'
                                   '加变体通常 non-breaking，但 exhaustive match 会破 —— 交给机器判',
                            'recheck': ['tools/r_semver.sh --baseline HEAD~1  # 机器判 enum 变体是否 breaking']}
                    add_finding(fname, rule, key=f'enum-variant:{fname}')
    return findings, rechecks


def self_test():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'✓' if cond else '✗'}] {name}")

    # 路径档
    f, r = analyze(['src/foo.rs'])
    check('普通模块无盲区', not r)
    f, r = analyze(['Cargo.toml'])
    check('Cargo.toml → DEPENDENCY-TREE', r and f[0]['level'] == 'DEPENDENCY-TREE' and len(r) == 3)
    f, r = analyze(['Cargo.lock'])
    check('Cargo.lock → LOCKFILE', r and f[0]['level'] == 'LOCKFILE')
    f, r = analyze(['benches/foo.rs'])
    check('benches → 无补验', not r)
    f, r = analyze(['build.rs'])
    check('build.rs → TOOLCHAIN', r and f[0]['level'] == 'TOOLCHAIN')

    # 内容档
    diff = {'src/lib.rs': {'added': ['    pub fn parse(s: &str) -> Result<Ast, Err> {', '    Ok(a)'], 'ctx': []}}
    f, r = analyze(['src/lib.rs'], diff)
    check('pub fn 变动 → API-SURFACE', r and any(x['level'] == 'API-SURFACE' for x in f))
    diff = {'src/buf.rs': {'added': ['    let v = unsafe { Vec::from_raw_parts(p, n, c) };'], 'ctx': []}}
    f, r = analyze(['src/buf.rs'], diff)
    check('新增 unsafe → SAFETY-BOUNDARY', r and any(x['level'] == 'SAFETY-BOUNDARY' for x in f))
    diff = {'src/net.rs': {'added': ['#[cfg(feature = "tls")]', 'fn tls_only() {}'], 'ctx': []}}
    f, r = analyze(['src/net.rs'], diff)
    check('cfg(feature) → FEATURE-MATRIX', r and any(x['level'] == 'FEATURE-MATRIX' for x in f))
    diff = {'src/m.rs': {'added': ['macro_rules! gen_thing {', '    () => { 42 }', '}'], 'ctx': []}}
    f, r = analyze(['src/m.rs'], diff)
    check('macro_rules → MACRO-WIDE', r and any(x['level'] == 'MACRO-WIDE' for x in f))
    # 普通 fn（非 pub）不触发
    diff = {'src/foo.rs': {'added': ['    fn helper() -> u32 { 42 }'], 'ctx': []}}
    f, r = analyze(['src/foo.rs'], diff)
    check('非 pub fn 不触发', not r)
    # enum 变体（e2e 实证盲区：KeyExpired 行无 pub 关键字，pub-api 规则看不见）
    diff = {'util/kerrno/src/lib.rs': {
        'added': ['    /// The required key has expired.', '    KeyExpired,'],
        'ctx': ['    FileTooLarge,', ' pub enum KErrorKind {']}}
    f, r = analyze(['util/kerrno/src/lib.rs'], diff)
    check('pub enum 加变体 → API-SURFACE(semver)', r and any(x['level'] == 'API-SURFACE' for x in f))
    # 反例：非 enum 上下文里的相似行不触发
    diff = {'src/foo.rs': {'added': ['    KeyExpired,'], 'ctx': ['    let x = 1;', '    // somewhere']}}
    f, r = analyze(['src/foo.rs'], diff)
    check('非 enum 上下文不误报', not r)

    # 组合：Cargo.toml + pub API + unsafe，recheck 合并去重
    diff = {'src/lib.rs': {'added': ['    pub fn new() -> Self { Self {} }'], 'ctx': []},
            'src/raw.rs': {'added': ['    let b = unsafe { &*(p as *const u8) };'], 'ctx': []}}
    f, r = analyze(['Cargo.toml', 'src/lib.rs', 'src/raw.rs'], diff)
    dup = len(r) != len(set(r))
    check(f'组合去重 ({len(r)} 条无重复, 3 个 level)', not dup and len(r) >= 5)
    print('self-test:', 'ALL PASS' if ok else 'FAILED')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', help='git base')
    ap.add_argument('--files', help='逗号分隔文件列表（相对 workspace）')
    ap.add_argument('--repo', default='.')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    added_by_file = None
    if args.files:
        paths = [x.strip() for x in args.files.split(',') if x.strip()]
    elif args.base:
        out = subprocess.run(f'git -C {args.repo} diff --name-only {args.base}',
                             shell=True, capture_output=True, text=True).stdout
        paths = [x for x in out.splitlines() if x.strip()]
        full = subprocess.run(f'git -C {args.repo} diff {args.base} --',
                              shell=True, capture_output=True, text=True).stdout
        added_by_file = parse_diff(full)
    else:
        ap.error('需要 --files 或 --base 或 --self-test')
        return 2

    findings, rechecks = analyze(paths, added_by_file)
    if args.json:
        print(json.dumps({'guard': 'blindspot', 'verdict': 'CLEAN' if not rechecks else 'RECHECK-REQUIRED',
                          'findings': findings, 'required_rechecks': rechecks},
                         ensure_ascii=False, indent=2))
    else:
        print(f'[blindspot] verdict={"CLEAN" if not rechecks else "RECHECK-REQUIRED"}')
        for f in findings:
            print(f"  {f['file']} [{f['level']}] {f['why']}")
        for r in rechecks:
            print(f'  → 补验: {r}')
        if rechecks:
            print('  → 手册 02 章：局部节点看不见的全局冲突，必须 graph 层补验后才准入队。')
    return 1 if rechecks else 0


if __name__ == '__main__':
    sys.exit(main())
