#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gujian 源码 → GitHub 同步脚本（REST API 直推，规避 github.com:443 不通）

- 仓库：g101400/gujian4060 (public)，分支：main
- 枚举：从仓库根目录(本脚本上级的上级)走文件系统，应用与 .gitignore 一致的排除规则
  （含 git 追踪 + 未追踪非忽略的全部文件）
- 自动排除：secrets/config.local.js、build/targets/keystore/、构建产物(*.apk/*.keystore 等)、
  .workbuddy、.github_token
- 幂等：本地 blob sha 与远端 contents API 返回的 sha 比对，相同则 SKIP
- 鉴权：优先 GITHUB_TOKEN 环境变量，否则回退 D:/Users/WorkBuddy/.github_token
- 输出一行机器可读汇总：PUSH_SUMMARY added=N updated=N skipped=N failed=N total=N
"""
import os
import sys
import base64
import hashlib
import json
import time
import urllib.request
import urllib.error
import urllib.parse

REPO = "g101400/gujian4060"
BRANCH = "main"
TOKEN_FILE = "D:/Users/WorkBuddy/.github_token"
API = "https://api.github.com"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # www 根目录

EXCLUDE_DIR_PREFIXES = (".git", ".workbuddy")
EXCLUDE_EXACT = (
    ".github_token",
    "secrets/config.local.js",
)
EXCLUDE_PATH_CONTAINS = (
    "build/targets/keystore",
)
EXCLUDE_SUFFIX = (".keystore", ".jks", ".apk", ".aab")


def is_excluded(rel):
    """rel 为 '/' 分隔的相对路径。"""
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    for p in parts:
        if p in EXCLUDE_DIR_PREFIXES:
            return True
    if rel in EXCLUDE_EXACT:
        return True
    for c in EXCLUDE_PATH_CONTAINS:
        if c in rel:
            return True
    for s in EXCLUDE_SUFFIX:
        if rel.endswith(s):
            return True
    return False


def get_token():
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"].strip()
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print(f"[AUTH] 无法读取 token: {e}", file=sys.stderr)
        return None


def blob_sha(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob " + str(len(data)).encode() + b"\x00" + data)
    return h.hexdigest()


def api(method, url, token, body=None, retries=4):
    last_err = None
    for attempt in range(retries):
        try:
            data = None
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": "gujian-push/1.0",
                "Accept": "application/vnd.github+json",
                "Accept-Encoding": "identity",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                j = json.loads(raw)
                msg = j.get("message", "")
            except Exception:
                msg = raw
            if e.code in (401, 403):
                # 鉴权/权限类错误，直接抛出终止
                raise RuntimeError(f"HTTP {e.code}: {msg}")
            last_err = f"HTTP {e.code}: {msg}"
            # 404 等用于"文件不存在"判断，由调用方处理，不重试
            if e.code == 404:
                return 404, {}
            time.sleep(1.0 * (attempt + 1))
        except Exception as e:  # 网络瞬时错误，重试
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(1.0 * (attempt + 1))
    return None, {"_error": last_err}


def list_files():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # 过滤排除目录
        dirnames[:] = [
            d for d in dirnames
            if not is_excluded(os.path.relpath(os.path.join(dirpath, d), ROOT).replace("\\", "/"))
        ]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace("\\", "/")
            if is_excluded(rel):
                continue
            out.append(rel)
    out.sort()
    return out


def main():
    token = get_token()
    if not token:
        print("[FATAL] 未找到 GITHUB_TOKEN 环境变量或 D:/Users/WorkBuddy/.github_token", file=sys.stderr)
        sys.exit(2)

    # 预检鉴权
    st, _ = api("GET", f"{API}/repos/{REPO}", token)
    if st != 200:
        print(f"[AUTH] 仓库访问失败 HTTP {st}（请检查 token 的 repo 权限）", file=sys.stderr)
        sys.exit(3)

    files = list_files()
    added = updated = skipped = failed = 0

    for rel in files:
        full = os.path.join(ROOT, rel)
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception as e:
            print(f"FAIL {rel} -> local read error: {e}")
            failed += 1
            continue

        local_sha = blob_sha(data)
        url = f"{API}/repos/{REPO}/contents/{urllib.parse.quote(rel, safe='/')}?ref={BRANCH}"

        st, j = api("GET", url, token)
        if st == 404:
            # 远端不存在 → 创建
            body = {
                "message": f"sync: add {rel}",
                "content": base64.b64encode(data).decode("ascii"),
                "branch": BRANCH,
            }
            st2, _ = api("PUT", url, token, body)
            if st2 in (200, 201):
                print(f"ADD  {rel}")
                added += 1
            else:
                print(f"FAIL {rel} -> create HTTP {st2}")
                failed += 1
            continue
        if st != 200:
            print(f"FAIL {rel} -> GET {st} {j.get('_error','')}")
            failed += 1
            continue

        remote_sha = j.get("sha")
        if remote_sha == local_sha:
            print(f"SKIP {rel}")
            skipped += 1
            continue

        # 内容不同 → 更新
        body = {
            "message": f"sync: update {rel}",
            "content": base64.b64encode(data).decode("ascii"),
            "sha": remote_sha,
            "branch": BRANCH,
        }
        st2, _ = api("PUT", url, token, body)
        if st2 in (200, 201):
            print(f"UPD  {rel}")
            updated += 1
        else:
            print(f"FAIL {rel} -> update HTTP {st2}")
            failed += 1

    total = added + updated + skipped + failed
    print(f"PUSH_SUMMARY added={added} updated={updated} skipped={skipped} failed={failed} total={total}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
