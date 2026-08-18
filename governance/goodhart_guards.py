#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""goodhart_guards.py — Graph 层治理之一：反 Goodhart 守卫（Rust 版）

手册 02 章 #65-66：in-loop 检查点（clippy 警告数、测试绿条）会被 gaming，
治法是上移 graph 层看 **diff 结构** 而非指标数值。

Rust 特性（为什么 Rust 版规则比 kernel 版多）：
  Rust 把 lint 抑制做成了语言一等公民 —— #[allow] / #[cfg] / unsafe / #[ignore]
  每个都是合法语法，也都是天然 gaming 通道。kernel 只有 #if 0 一种土办法；
  Rust 有整整一层"看起来很专业"的抑制原语，所以守卫规则必须更懂语言惯例。

守卫规则（每条对应一种已知 gaming 手法）:
  G1 净删除率 > 40% 且任务非标注删除          —— "删代码消 clippy 警告"
  G2 新增行注释占比 > 50%                     —— "注释掉报警代码"
  G3 抑制标记 #[allow] / --cap-lints / 删 #[deny(warnings)]
  G4 空 diff / 纯 whitespace 变化             —— "空 commit 骗绿"
  G5 #[cfg(not(test))] / #[cfg(feature)] 包裹存量代码 —— "条件编译掉警告/测试路径"
  G6 新增 unsafe 块无对应 // SAFETY: 论证     —— "safe 抽象层下的 UB 转移"
  G7 src/ 新增 panic 通道密度（unwrap/todo!/panic! ≥3）—— "编译过≠对，把失败推迟到运行时"
  G8 测试逃逸：+#[ignore] / -#[test]          —— "删测试消红"（tests/ 内 unwrap 豁免——那是惯例）

用法:
  python3 goodhart_guards.py --base HEAD~1 [--repo DIR] [--task-type add]
  python3 goodhart_guards.py --diff my.patch [--task-type add]
  python3 goodhart_guards.py --self-test

退出码: 0=PASS  1=REJECT(有 gaming 证据)  2=用法/环境错
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

SUPPRESS_PATTERNS = [
    r'#\s*!\s*\[allow\(',          # 内层 allow（crate 级）
    r'#\s*\[allow\(',              # 条目级 allow
    r'#\s*\[cfg_attr\([^)]*allow', # 条件 allow
    r'--cap-lints',                # 命令行级压制（最恶劣）
    r'intra_doc_resolution',       # rustdoc lint 压制的常见别名
]
DENY_WARN_DEL = re.compile(r'^-.*#\s*!?\s*\[deny\(.*warnings')   # 删掉全局警告门
COMMENT_RE = re.compile(r'^\s*(/\*|//|\*|#)')

# 配对消除规模保护：SequenceMatcher 是 O(n²)，超过此行数退回保守 max(0, rem-add)
_PAIRING_CAP = 2000


def net_removed(added, removed):
    """改写对配对消除后的真实删除行数（G1 准确语义，与 kernel 版同源）。

    difflib get_opcodes：equal→0 / replace→净删 / delete→全算；
    大 diff 退回保守近似。
    """
    if not removed:
        return 0
    if len(added) + len(removed) > _PAIRING_CAP:
        return max(0, len(removed) - len(added))
    sm = difflib.SequenceMatcher(None, removed, added, autojunk=False)
    real = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'delete':
            real += i2 - i1
        elif tag == 'replace':
            real += max(0, (i2 - i1) - (j2 - j1))
    return real

UNSAFE_RE = re.compile(r'\bunsafe\b\s*(\{|\s+fn|\s+impl|trait)')
SAFETY_NOTE_RE = re.compile(r'(//\s*SAFETY|///\s*#\s*Safety)')
PANIC_RE = re.compile(r'(\.unwrap\(\)|\btodo!\(|\bunimplemented!\(|\bpanic!\(|\bunreachable!\()')
TEST_ESCAPE_RE = re.compile(r'#\s*\[(ignore|cfg\(not\(test\)\))')


def sh(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {cmd}\n{r.stderr}")
    return r.stdout


def parse_diff(diff_text):
    """解析 unified diff → 每文件 added[]/removed[]（跳过 +++/--- 头与 hunk 行）"""
    files, cur = {}, None
    for line in diff_text.splitlines():
        if line.startswith('+++ b/'):
            cur = line[6:]
            files[cur] = {'added': [], 'removed': []}
        elif line.startswith('--- a/'):
            continue
        elif cur is not None:
            if line.startswith('+') and not line.startswith('+++'):
                files[cur]['added'].append(line[1:])
            elif line.startswith('-') and not line.startswith('---'):
                files[cur]['removed'].append(line[1:])
    return files


def is_test_path(fname):
    """tests/ 目录与 *_test.rs / test.rs 后缀：panic 通道在此是 Rust 惯例，豁免 G7"""
    return '/tests/' in f'/{fname}' or fname.endswith(('_test.rs', '/test.rs', 'tests.rs'))


def guard(diff_text, task_type='add'):
    """返回 (verdict, findings[])。verdict: PASS|REJECT"""
    findings = []
    files = parse_diff(diff_text)
    if not files:
        return 'REJECT', [{'rule': 'G4', 'detail': '空 diff —— 无行为变化的提交不能进队列'}]

    for fname, ch in files.items():
        added, removed = ch['added'], ch['removed']
        n_add, n_rem = len(added), len(removed)
        test_scope = is_test_path(fname)

        # G4: 纯 whitespace
        if all(a.strip() == '' for a in added) and all(r.strip() == '' for r in removed) and n_add + n_rem > 0:
            findings.append({'rule': 'G4', 'file': fname, 'detail': '纯 whitespace 变化'})

        # G1: 配对消除净删除率（v3：difflib 改写对消除——kernel e2e 教训的根治版）
        total = n_add + n_rem
        if total >= 10 and task_type not in ('del', 'cleanup', 'refactor'):
            real_del = net_removed(added, removed)
            del_ratio = real_del / total
            if del_ratio > 0.4:
                findings.append({'rule': 'G1', 'file': fname,
                                 'detail': f'配对消除后净删除占比 {del_ratio:.0%}（真删 {real_del}/{n_rem}，改写对已消除）—— 疑似删代码消 clippy 警告；确属删除任务请 --task-type del'})

        # G2: 注释占比（Rust 版含 /// doc comment）
        code_add = [a for a in added if a.strip()]
        if len(code_add) >= 8:
            cmt = sum(1 for a in code_add if COMMENT_RE.match(a))
            if cmt / len(code_add) > 0.5:
                findings.append({'rule': 'G2', 'file': fname,
                                 'detail': f'新增行注释占比 {cmt}/{len(code_add)} —— 疑似注释掉报警代码'})

        # G3: 抑制标记（Rust 的合法语法 = 天然 gaming 通道）
        for pat in SUPPRESS_PATTERNS:
            for a in added:
                if re.search(pat, a):
                    findings.append({'rule': 'G3', 'file': fname, 'detail': f'抑制标记: {a.strip()[:80]}'})
                    break
        for r in removed:
            if DENY_WARN_DEL.search(r):
                findings.append({'rule': 'G3', 'file': fname, 'detail': f'删除警告门: {r.strip()[:80]}'})

        # G5: cfg 包裹存量代码（条件编译掉路径）
        if not test_scope:
            for a in added:
                if re.search(r'#\s*\[cfg\((not\(test\)|feature\s*=)', a):
                    findings.append({'rule': 'G5', 'file': fname, 'detail': f'cfg 屏蔽路径: {a.strip()[:80]}'})
                    break

        # G6: 新增 unsafe 无 SAFETY 论证（Rust 特有：unsafe 的契约编译器不查，守卫查）
        if not test_scope:
            n_unsafe = sum(len(UNSAFE_RE.findall(a)) for a in added)
            n_safety = sum(len(SAFETY_NOTE_RE.findall(a)) for a in added)
            if n_unsafe > 0 and n_safety < n_unsafe:
                findings.append({'rule': 'G6', 'file': fname,
                                 'detail': f'新增 {n_unsafe} 处 unsafe 但 SAFETY 论证仅 {n_safety} 处 —— 每个 unsafe 块前须 // SAFETY: 写明 invariant'})

        # G7: src/ 生产代码 panic 通道密度（tests/ 豁免 —— unwrap 在测试里是惯例）
        if not test_scope and len(code_add) >= 8:
            n_panic = sum(len(PANIC_RE.findall(a)) for a in added)
            if n_panic >= 3:
                findings.append({'rule': 'G7', 'file': fname,
                                 'detail': f'新增 panic 通道 {n_panic} 处（unwrap/todo!/panic!）—— 生产路径用 Result/?,把失败编译期化/传播化'})

        # G8: 测试逃逸（+#[ignore] / -#[test]）
        for a in added:
            if TEST_ESCAPE_RE.search(a):
                findings.append({'rule': 'G8', 'file': fname, 'detail': f'测试逃逸: {a.strip()[:80]}'})
                break
        n_test_del = sum(1 for r in removed if re.search(r'#\s*\[test\]', r))
        if n_test_del > 0:
            findings.append({'rule': 'G8', 'file': fname, 'detail': f'删除 {n_test_del} 个 #[test] —— 删测试消红 = 最重级 gaming'})

    return ('REJECT' if findings else 'PASS'), findings


def self_test():
    """gaming 样本必 REJECT，正常修复必 PASS。"""
    # 改写对回归（kernel e2e 教训：±1 改写不是删除，必须 PASS）
    rewrite_pair = ('+++ b/src/main.rs\n@@\n' + '\n'.join(f'-    let v{i} = old_call_{i}();' for i in range(10))
                    + '\n' + '\n'.join(f'+    let v{i} = new_call_{i}();' for i in range(9)))
    cases = [
        ('正常修复(Result 传播)', 'add', """+++ b/src/parser.rs
@@
-    let n: i32 = s.parse().unwrap();
-    return n;
+    let n: i32 = s.parse().map_err(|e| ParseError::new(e))?;
+    Ok(n)
""", 'PASS'),
        ('有 SAFETY 论证的 unsafe', 'add', """+++ b/src/buf.rs
@@
+    // SAFETY: `ptr` comes from `Box::into_raw` above; length matches capacity;
+    // no aliasing references exist in this scope.
+    let v = unsafe { Vec::from_raw_parts(ptr, len, cap) };
+    Ok(v)
""", 'PASS'),
        ('改写对 9+/10- 不误报(净删除语义)', 'add', rewrite_pair, 'PASS'),
        ('G1 删代码消警告', 'add', """+++ b/src/legacy.rs
@@
-    let r = legacy_path_a(x);
-    if r < 0 {
-        eprintln!("path a fail");
-        return r;
-    }
-    let r2 = legacy_path_b(x);
-    if r2 < 0 {
-        eprintln!("path b fail");
-        return r2;
-    }
-    return r + r2;
+    0
""", 'REJECT'),
        ('G3 #[allow] 压制', 'add', """+++ b/src/foo.rs
@@
+    #[allow(clippy::needless_range_loop)]
+    for i in 0..v.len() {
+        s += v[i];
+    }
+    Ok(s)
""", 'REJECT'),
        ('G6 unsafe 无 SAFETY', 'add', """+++ b/src/buf.rs
@@
+    let v = unsafe { Vec::from_raw_parts(ptr, len, cap) };
+    let w = unsafe { std::slice::from_raw_parts(p2, n) };
+    Ok((v, w))
""", 'REJECT'),
        ('G7 unwrap 密度', 'add', """+++ b/src/main.rs
@@
+    let a = parts.next().unwrap();
+    let b = parts.next().unwrap();
+    let c = parts.next().unwrap();
+    let n: i32 = a.parse().unwrap();
+    let m = std::mem::size_of_val(a);
+    let v = vec![n, m as i32];
+    let s: String = b.to_owned();
+    println!("{}", v.len() + s.len() + c.len());
""", 'REJECT'),
        ('G7 tests/ 内 unwrap 豁免', 'add', """+++ b/tests/parser_test.rs
@@
+    let got = run("a b c").unwrap();
+    let got2 = run("d e").unwrap();
+    let got3 = run("f").unwrap();
+    let got4 = run("").unwrap_err();
+    assert_eq!(got.len(), 3);
+    assert_eq!(got2.len(), 2);
+    assert_eq!(got3.len(), 1);
+    assert!(got4.is_empty_err());
""", 'PASS'),
        ('G8 删 #[test]', 'add', """+++ b/tests/parser_test.rs
@@
-    #[test]
-    fn rejects_bad_input() {
-        assert!(run("!!!").is_err());
-    }
+    // covered manually
""", 'REJECT'),
    ]
    ok = True
    for name, ttype, diff, expect in cases:
        verdict, f = guard(diff, ttype)
        mark = '✓' if verdict == expect else '✗'
        ok = ok and (verdict == expect)
        print(f"  [{mark}] {name}: {verdict} (expect {expect}) findings={len(f)}")
    print('self-test:', 'ALL PASS' if ok else 'FAILED')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', help='git base，如 HEAD~1')
    ap.add_argument('--diff', help='直接给 diff 文件路径')
    ap.add_argument('--repo', default='.')
    ap.add_argument('--task-type', default='add', choices=['add', 'del', 'cleanup', 'refactor'])
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.diff:
        diff_text = Path(args.diff).read_text(errors='replace')
    elif args.base:
        diff_text = sh(f'git -C {args.repo} diff {args.base} --', check=False)
    else:
        ap.error('需要 --base 或 --diff 或 --self-test')
        return 2

    verdict, findings = guard(diff_text, args.task_type)
    if args.json:
        print(json.dumps({'guard': 'goodhart', 'verdict': verdict, 'findings': findings},
                         ensure_ascii=False, indent=2))
    else:
        print(f'[goodhart] verdict={verdict}')
        for f in findings:
            print(f"  {f['rule']} {f.get('file', '')}: {f['detail']}")
        if verdict == 'REJECT':
            print('  → 手册 02 章：指标被 gaming，loop 层看不见，已由 graph 层拦截。记账 REJECT。')
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
