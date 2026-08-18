#!/usr/bin/env python3
# post-issues.py — 4 份草稿逐条投 gitee issue（token 从 env 读，不落盘）
import json
import os
import re
import sys
import urllib.parse
import urllib.request

TOKEN = os.environ['GITEE_TOKEN']
API = 'https://gitee.com/api/v5/repos/openkylin/issues'   # gitee v5：owner 级端点 + repo 参数
DRAFTS = [
    'issues/x-kernel/01-fmt-debt-and-ci-gate.md',
    'issues/x-kernel/02-kext4-panic-density.md',
    'issues/x-kernel/03-cfg-unittest-undeclared.md',
    'issues/x-kernel/04-precommit-toolchain-hint.md',
]

ok = fail = 0
for path in DRAFTS:
    text = open(path, encoding='utf-8').read()
    title = text.splitlines()[0].lstrip('# ').strip()
    body = '\n'.join(text.splitlines()[1:]).strip()
    data = urllib.parse.urlencode({
        'access_token': TOKEN, 'repo': 'x-kernel',
        'title': title, 'body': body,
    }).encode()
    req = urllib.request.Request(API, data=data, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode('utf-8', errors='replace')
        d = json.loads(re.sub(r'[\x00-\x1f]', ' ', raw))
        url = d.get('html_url')
        if url:
            print(f'[ok] {title} -> {url}')
            ok += 1
        else:
            print(f'[fail] {title} -> {d.get("message")}')
            fail += 1
    except Exception as e:
        print(f'[fail] {title} -> {e}')
        fail += 1
print(f'done: {ok} ok, {fail} fail')
sys.exit(0 if fail == 0 else 1)
