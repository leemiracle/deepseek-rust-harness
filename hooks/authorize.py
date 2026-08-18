#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""authorize.py — Scope 子系统 + L 组件：fail-closed 权限门（Rust 版）

手册 03 章：authorize_tool_call 是 L 组件核心挂点；**fail-closed：无规则 = 拒绝**。
Rust 场景特化：
  - 不可撤回操作黑名单（cargo publish / rustup 全局态 / 毁增量基线）
  - 命令行级警告压制 = Goodhart 通道（RUSTFLAGS=-A / --cap-lints）
  - cargo install 从源码编译执行 build.rs = 任意代码执行，同 curl|sh 级
  - 写路径白名单（workspace + 本插件 state/）
用法（CLI 自测）:
  python3 hooks/authorize.py            # 跑内置断言组
被 rust_host.py 以模块方式调用: from hooks.authorize import authorize
"""
import os
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

TOOLS = {'read_file', 'grep_tree', 'run_verify', 'write_file',
         'r_fmt', 'r_lint', 'r_build', 'r_miri', 'r_audit', 'r_semver',
         'graph_guard', 'graph_conflict', 'patch_queue', 'deep_plan'}

# 危险命令模式 → 拒绝理由（agent 看得懂，报错即导航）
DENY_PATTERNS = [
    (r'\bcargo\s+publish\b', 'cargo publish 不可撤回：crates.io 版本号永久占用（yank 只隐藏不解绑）。发布须人工'),
    (r'\brustup\s+(self\s+)?(uninstall|update)\b|\brustup\s+(default|override)\b',
     'rustup 动全局 toolchain 状态：所有 workspace 的编译器版本都会被改'),
    (r'\bcargo\s+clean\b', 'cargo clean 毁增量基线（fingerprint 全丢，下次全量重编依赖树）'),
    (r'\brm\s+(-[a-zA-Z]*f[a-zA-Z]*|--)\s*[^ ]*target', 'rm -rf target 同 cargo clean：毁增量基线'),
    (r'\brm\s+(-[a-zA-Z]*f[a-zA-Z]*|--)', 'rm -f 系列被拦：删除请精确到文件名'),
    (r'\bgit\s+push\s+(-f|--force)', 'force-push 毁历史'),
    (r'\bmake\s+(mrproper|distclean)', '遗留 kernel 习惯：当前项目无 make，疑似跑错目录'),
    (r'\bchmod\s+777', '世界可写是事故起点'),
    (r'\bcurl[^|]*\|\s*(ba)?sh', '管道执行远程代码，Scope 红线'),
    (r'\bwget[^|]*\|\s*(ba)?sh', '同上'),
    (r'\bcargo\s+install\b[^&|;]*--(git|path)\b', 'cargo install --git/--path 编译并执行任意 build.rs = 远程码执行'),
    (r'\b(reboot|shutdown|init\s+0)\b', '宿主机不是你的测试机'),
    (r'\bgit\s+reset\s+--hard', '硬重置会吞掉其他 series 的未提交工作'),
]

# Goodhart 通道：命令行级警告压制（语言内 #[allow] 由 governance 在 diff 层查，这里查 shell 层）
DENY_PATTERNS += [
    (r'RUSTFLAGS=[^&|;]*-A\s*(warnings|clippy)', 'RUSTFLAGS=-A 在命令行压制警告 = Goodhart 通道（手册 02 章）；豁免走 diff review'),
    (r'--cap-lints\b', '--cap-lints 压制整 crate 警告 = Goodhart 通道；不许'),
    (r'cargo\s+clippy[^&|;]*\s--\s.*-A\s', 'clippy -A 在命令行豁免 lint = Goodhart 通道；单条豁免走 diff review'),
]


# 可写白名单（前缀匹配）：workspace（由 RUST_PROJECT 声明）+ 插件 state/
def _writable_roots():
    roots = [str(PLUGIN_ROOT / 'state')]
    ws = _rust_project()
    if ws:
        roots.append(str(ws))
    return roots


def _rust_project():
    env = os.environ.get('RUST_PROJECT', '')
    if env and Path(env).is_dir():
        return Path(env).resolve()
    for cand in (PLUGIN_ROOT, PLUGIN_ROOT.parent):
        if (cand / 'Cargo.toml').is_file():          # 插件常住在 workspace 内
            return cand.resolve()
    return None


def authorize(tool_name, args):
    """返回 (allowed: bool, reason: str)。fail-closed：未注册工具一律拒。"""
    if tool_name not in TOOLS:
        return False, f'unknown tool "{tool_name}" — fail-closed（手册 03 章：无规则=拒绝）'

    cmd = str(args.get('cmd', ''))
    for pat, why in DENY_PATTERNS:
        if re.search(pat, cmd):
            return False, f'DENIED: {why} (pattern: {pat})'

    # 写路径检查
    if tool_name == 'write_file':
        p = str(args.get('path', ''))
        if not p:
            return False, 'write_file 需要 path'
        rp = Path(p).resolve()
        if not any(str(rp).startswith(r) for r in _writable_roots()):
            return False, f'DENIED: 写白名单外路径 {rp}（允许: RUST_PROJECT + state/）'
    return True, 'ok'


def _self_test():
    cases = [
        ('run_verify', {'cmd': 'cargo clippy --workspace --all-targets -- -D warnings'}, True),
        ('run_verify', {'cmd': 'cargo publish --dry-run'}, False),          # publish 连 dry-run 都禁（提示语义误导）
        ('run_verify', {'cmd': 'cargo clean'}, False),                      # 毁增量基线
        ('run_verify', {'cmd': 'RUSTFLAGS="-A warnings" cargo build'}, False),  # Goodhart 通道
        ('run_verify', {'cmd': 'cargo clippy -- -A clippy::all'}, False),   # Goodhart 通道
        ('run_verify', {'cmd': 'cargo build --cap-lints allow'}, False),    # Goodhart 通道
        ('run_verify', {'cmd': 'cargo install --git https://x/r.git t'}, False),  # 编译执行远程码
        ('run_verify', {'cmd': 'rustup default nightly'}, False),           # 动全局态
        ('run_verify', {'cmd': 'rm -rf target/debug'}, False),              # 毁基线+rm -f 系
        ('run_verify', {'cmd': 'rm /tmp/precise_file'}, True),              # 精确删除 OK
        ('run_verify', {'cmd': 'cargo test --workspace'}, True),
        ('write_file', {'path': str(PLUGIN_ROOT / 'state' / 'progress.md')}, True),
        ('write_file', {'path': '/etc/passwd'}, False),                     # 白名单外
        ('nuclear_launch', {'cmd': 'x'}, False),                            # 未注册工具
    ]
    ok = True
    for tool, args, want in cases:
        got, why = authorize(tool, args)
        mark = '✓' if got == want else '✗'
        ok = ok and (got == want)
        print(f'  [{mark}] {tool} {str(args)[:52]:52} -> {"ALLOW" if got else "DENY"}  {"" if got else why[:60]}')
    print('self-test:', 'ALL PASS' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(_self_test())
