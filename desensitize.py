#!/usr/bin/env python3
"""
desensitize.py —— 生成「可公开」的脱敏版本，与「带原文」的内部版本并存。

为什么要有两份
──────────────
内部 `themes/` 与 `my-styles/` 里存的是**参考文章的身份信息**：原文标题、公众号名、
文章链接。这些是溯源用的，删了以后自己想「回头看看当初那篇到底长什么样」就没路了。
但同一批文件一旦进公开仓库，等于替别人的文章打了标签。

所以：原文照留，另开一套脱敏版 `themes-public/` + `my-styles-public/` 进公开树。
脱敏是**确定性变换**（不是手改一遍），以后新提一个主题再跑一次就自动带上。

脱敏规则（只删身份，不删排版能力）
──────────────────────────────────
* 删：原文标题、公众号名、文章链接
* 留：全部色值、字号、行高、段距、组件计数 —— 这些是观察结果，
      能反推排版，但不指向任何一篇文章
* 留：主题短名（owner 自己起的 `_name`，不含原文信息）
* 留：`_originalColors`，改坏了能照原色还原
* 打标记：`_desensitized: true`

用法
────
    python3 desensitize.py            # 重新生成两份脱敏目录
    python3 desensitize.py --check    # 只体检：公开目录里是否还残留原文信息
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE_DIR = os.path.join(HERE, "my-styles")
THEME_DIR = os.path.join(HERE, "themes")
STYLE_PUB = os.path.join(HERE, "my-styles-public")
THEME_PUB = os.path.join(HERE, "themes-public")

# 这些字段一旦非空就说明原文身份漏出去了
IDENTITY_FIELDS = ("sourceUrl", "title", "author")
# 连续这么长的中文，正常主题文件里不该出现（都是 CSS / 色值 / 短标签），
# 出现了多半是没删干净的原文标题。阈值取 10 是为了不误伤「引用/重点提示」这类短词。
CJK_RUN = re.compile(r"[一-鿿]{8,}")
# 脱敏脚本自己写进去的两句通用文案（以及 style_to_theme 写死的 note）。
# 白名单按**内容**比，不按字段名比：这样一旦有人往 _readme 里塞了原文标题，
# 内容对不上白名单，照样报漏。
# 以下键名整体删除（它们是身份字段的容器，留个空壳没意义）
DROP_KEYS = ("_from",)

DESENSITIZE_README = ("由参考文章的排版参数自动生成，色值已做过白底对比度校验。"
                      "本文件已去除原文标题、公众号名与文章链接，不含任何身份信息。")
# 脱敏脚本自己写进去的一般说明（以及 style_to_theme 写死的那句 note）。
# 白名单按**内容**比，不按字段名比：一旦有人往 _readme 里塞了原文标题，
# 内容对不上白名单，照样报漏。
ORIGIN_NOTE = "下面是提取时套用前的原色，改坏了可以照着还原"
TRUSTED_TEXT = frozenset({DESENSITIZE_README, ORIGIN_NOTE})


# ────────────────────────────────────────────────────────────────
def scrub(obj, path: str = ""):
    """递归清掉身份信息，其余（色值/数字/CSS/短名）原样保留。"""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in DROP_KEYS:
                continue
            out[key] = scrub(value, f"{path}.{key}" if path else key)
        for key in IDENTITY_FIELDS:
            if key in out:
                out[key] = ""
        return out
    if isinstance(obj, list):
        return [scrub(item, path) for item in obj]
    if isinstance(obj, str):
        # tokens[].value 里偶尔会带链接，一并摘掉
        return "" if re.search(r"mp\.weixin\.qq\.com|https?://", obj) else obj
    return obj


def build_public_style(style: dict) -> dict:
    public = scrub(style)
    public["_desensitized"] = True
    public["_desensitizedAt"] = datetime.now().strftime("%Y-%m-%d")
    return public


def build_public_theme(theme: dict) -> dict:
    public = scrub(theme)
    public["_readme"] = DESENSITIZE_README
    public["_desensitized"] = True
    public["_desensitizedAt"] = datetime.now().strftime("%Y-%m-%d")
    return public


# ────────────────────────────────────────────────────────────────
def generate() -> int:
    made = 0
    for src, dst_dir, builder in (
        (STYLE_DIR, STYLE_PUB, build_public_style),
        (THEME_DIR, THEME_PUB, build_public_theme),
    ):
        if not os.path.isdir(src):
            print(f"[skip] 源目录不存在：{src}")
            continue
        os.makedirs(dst_dir, exist_ok=True)
        for path in sorted(glob.glob(os.path.join(src, "*.json"))):
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
            out = os.path.join(dst_dir, os.path.basename(path))
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(builder(raw), fh, ensure_ascii=False, indent=2)
            print(f"[public] {os.path.basename(path)} -> {out}")
            made += 1
    print(f"\n共 {made} 个文件。公开前跑一次 --check 体检。")
    return 0


# ────────────────────────────────────────────────────────────────
def find_leaks(obj, trail: str = "") -> list[str]:
    """找出公开目录里残留的原文身份信息。"""
    leaks: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in IDENTITY_FIELDS and isinstance(value, str) and value.strip():
                leaks.append(f"{trail}.{key} = {value[:40]!r}")
            leaks.extend(find_leaks(value, f"{trail}.{key}" if trail else key))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            leaks.extend(find_leaks(item, f"{trail}[{idx}]"))
    elif isinstance(obj, str):
        if obj in TRUSTED_TEXT:
            return leaks                       # 固定通用文案，自己写的，不是原文
        if re.search(r"mp\.weixin\.qq\.com|https?://", obj):
            leaks.append(f"{trail} = {obj[:60]!r}")
        else:
            hit = CJK_RUN.search(obj)
            if hit:
                around = obj[max(0, hit.start() - 8): hit.end() + 8]
                leaks.append(f"{trail} 疑似原文标题（长中文）：…{around}…")
    return leaks


def check() -> int:
    total = 0
    bad = 0
    for dst_dir in (STYLE_PUB, THEME_PUB):
        if not os.path.isdir(dst_dir):
            print(f"[skip] 还没生成：{dst_dir}（先跑一次不带 --check 的）")
            continue
        for path in sorted(glob.glob(os.path.join(dst_dir, "*.json"))):
            total += 1
            with open(path, encoding="utf-8") as fh:
                leaks = find_leaks(json.load(fh))
            if leaks:
                bad += 1
                print(f"[LEAK] {os.path.basename(path)}")
                for one in leaks[:5]:
                    print(f"        {one}")
    if not total:
        print("公开目录是空的，脱敏版还没生成。")
        return 1
    if bad:
        print(f"\n✗ {bad}/{total} 个文件仍带身份信息，先回到内部版本删干净再重新生成。")
        return 1
    print(f"✓ {total} 个公开文件无身份残留（无原文标题 / 无公众号名 / 无文章链接）。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成并体检脱敏公开版")
    ap.add_argument("--check", action="store_true", help="只体检，不重新生成")
    args = ap.parse_args()
    return check() if args.check else generate()


if __name__ == "__main__":
    raise SystemExit(main())
