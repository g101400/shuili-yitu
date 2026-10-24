#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
shuili 源码 → GitHub 同步脚本（REST API 直推，规避 github.com:443 不通）

- 仓库：g101400/shuili-yitu (public)，分支：main
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

REPO = "g101400/shuili-yitu"
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


# ---- 推送前硬门禁（2026-10-23 第 59 轮新增，形态 ㊺）-----------------------------
# 为什么加：2026-10-23 实测三仓 webroot/secure_boot_cred.js（199B，AES-GCM 加盐凭证）
#   已被 git 追踪并推上 **public** 仓，匿名请求 API 即可解出明文。
#   当时 EXCLUDE_EXACT 里没有它，is_excluded() 对它是零覆盖 ——
#   门禁若只按"排除清单"判，就永远看不见清单外的东西（㊸ 教训）。
# 本函数不读排除清单，按**文件性质**独立扫即将上传的字节：命中即 ABORT，零上传。
SENSITIVE_NAMES = ("secure_boot_cred.js", "ai_seed.js", ".github_token",
                    "sec_crypt.js")   # 2026-10-23 实跑新抓：含同一套 AES-GCM 加盐参数
ALLOW_NAMES = ("ai_seed.demo.js",)          # 公开占位模板，允许上传
# 内容口径（2026-10-23 首轮实跑抓到的两条**误报**已收窄，详见下方 note）：
#   · "sk-or-v1" 会命中 push.py **自身**（它就是常量字面量）与 __pycache__ 里的 .pyc
#     → 门禁自匹配，属假红（㊸ 已踩过一次，此处复发，故加 SELF_SKIP）。
#   · "__SEC_BOOT" 会命中 secure_boot.js（13KB 访问口令门**程序**，变量名而已）
#     和 security 相关 4 份 iOS 壳脚本 → 不是凭据，属假红。真凭据靠**文件名**抓。
#   → 收敛为「真实凭据形态」：OpenRouter key 的完整前缀 + GitHub PAT + 加盐凭证的 JSON 骨架。
SENSITIVE_CONTENT_PATTERNS = (
    "sk-or-v1-",                             # OpenRouter 真 key（带连字符，降低误配）
    "github_pat_11",                         # GitHub fine-grained PAT
    '"alg":"AES-GCM-256","iter"',            # secure_boot_cred.js 的真实骨架
)
# 自匹配豁免：门禁/推送脚本自身与字节码缓存不算待传内容
SELF_SKIP_NAMES = ("push.py", "push_public.py")
SELF_SKIP_PATH_PARTS = ("__pycache__/",)


def scan_secrets(files):
    """返回 (hits, content_hits)。hits=按文件名命中；content_hits=按内容口径命中。"""
    hits, content_hits = [], []
    for rel in files:
        rel_n = rel.replace("\\", "/")
        base = rel_n.rsplit("/", 1)[-1]
        if base in ALLOW_NAMES:
            continue
        if base in SELF_SKIP_NAMES or any(p in rel_n for p in SELF_SKIP_PATH_PARTS):
            continue
        if base in SENSITIVE_NAMES:
            hits.append(rel)
            continue
        try:
            with open(os.path.join(ROOT, rel), "rb") as f:
                head = f.read(200000).decode("utf-8", "replace")
        except Exception:
            continue
        for pat in SENSITIVE_CONTENT_PATTERNS:
            if pat in head:
                content_hits.append("%s <- %s" % (rel, pat))
                break
    return hits, content_hits


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

    # ---- 推送前硬门禁：按文件性质扫，不看排除清单（命中即零上传退出）
    sec_hits, content_hits = scan_secrets(files)
    if sec_hits or content_hits:
        print("[ABORT] 敏感件拦截，未发起任何 GitHub 写入", file=sys.stderr)
        for h in sec_hits:
            print("  [NAME] %s" % h, file=sys.stderr)
        for h in content_hits:
            print("  [CONTENT] %s" % h, file=sys.stderr)
        print("PUSH_SUMMARY added=0 updated=0 skipped=0 failed=0 total=0 ABORTED_SECRET=1")
        sys.exit(4)

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
