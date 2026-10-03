#!/usr/bin/env python3
"""
公众号 HTML 校验器 —— 0 ERROR 门槛。

用法:
  python3 validate_gzh_html.py 文章.html
  python3 validate_gzh_html.py --theme          # 只自检组件库
  python3 validate_gzh_html.py --max-warn 3     # 允许 N 条 WARN 才不算失败

退出码: 0 = 通过（ERROR 0 且 WARN <= max-warn）；1 = 不通过。

ERROR 规则（微信会过滤/错乱，必须零容忍）:
  R1  出现 <div>                     微信编辑器解析错乱
  R2  出现 <style>/<script>/<link>/<iframe>
  R3  出现 class= / id= 属性          样式会被剥离
  R4  出现 position:/float:/@media/display:flex|grid/var(
  R5  裸文本节点（不在 <span> 内的中文字符）  微信会重写排版
  R6  <img> 缺 style
  R7  标签未闭合（粗检）
WARN 规则（建议但不阻断）:
  W1  代码块没深色底
  W2  含外链 href
  W3  中文直引号 "  '
  W4  h2 没有左侧竖条（border-left），这个版式的识别点丢了
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
THEME_PATH = os.path.join(HERE, "components", "local-theme.json")

BANNED_TAGS = ("div", "style", "script", "link", "iframe", "body", "html", "head", "form")
BANNED_ATTR = re.compile(r"\b(class|id|data-[a-z-]+)\s*=", re.I)
BANNED_PROPS = re.compile(
    r"(position\s*:|float\s*:|@media|display\s*:\s*(inline-)?flex|display\s*:\s*grid|var\s*\()", re.I
)
CJK = re.compile(r"[\u4e00-\u9fff]")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, rule: str, msg: str, line: int = 0) -> None:
        self.errors.append(f"[{rule}]{' L' + str(line) if line else ''} {msg}")

    def warn(self, rule: str, msg: str, line: int = 0) -> None:
        self.warnings.append(f"[{rule}]{' L' + str(line) if line else ''} {msg}")


SPAN_TAG = re.compile(r"<\s*/?\s*span[\s>/]", re.I)


def check_span_wrap(text: str, rep: Report) -> None:
    """R5：裸文本节点 = 不在任何 <span> 内部的中文字符。

    用深度计数而不是布尔量 —— 行内加粗/斜体是 <span> 套 <span>，
    布尔量会在内层 </span> 闭合时把外层也误判成脱离。
    """
    i, n = 0, len(text)
    depth = 0
    while i < n:
        ch = text[i]
        if ch == "<":
            close = text.find(">", i)
            if close == -1:
                return
            frag = text[i:close + 1]
            if SPAN_TAG.match(frag):
                if frag.rstrip().endswith("/>"):
                    pass  # 自闭合 span 不进栈
                elif frag.startswith("<"):
                    depth += 1
                else:
                    depth = max(0, depth - 1)
            i = close + 1
            continue
        if depth == 0 and CJK.match(ch):
            j = i
            while j < n and text[j] != "<":
                j += 1
            line_no = text.count("\n", 0, i) + 1
            snippet = text[i:j][:40].replace("\n", " ")
            rep.err("R5", f"裸文本节点未包 <span>：…{snippet}…", line_no)
            i = j
            continue
        i += 1


def validate(html_text: str, rep: Report) -> None:
    lines = html_text.split("\n")

    # R1 / R2 标签
    for tag in BANNED_TAGS:
        if re.search(rf"<{tag}[\s>]", html_text, re.I):
            for idx, line in enumerate(lines, 1):
                if re.search(rf"<{tag}[\s>]", line, re.I):
                    rep.err("R1" if tag == "div" else "R2",
                            f"禁止标签 <{tag}>", idx)
                    break

    # R3 属性
    for idx, line in enumerate(lines, 1):
        if BANNED_ATTR.search(line):
            hit = BANNED_ATTR.search(line).group(1)
            rep.err("R3", f"存在被微信剥离的属性 class=/id=（命中 {hit}）", idx)
            break

    # R4 内联属性
    for idx, line in enumerate(lines, 1):
        if BANNED_PROPS.search(line):
            hit = BANNED_PROPS.search(line).group(0)
            rep.err("R4", f"存在微信不支持的 CSS：{hit}", idx)
            break

    # R5 裸文本
    check_span_wrap(html_text, rep)

    # R6 img 必须有 style
    for idx, line in enumerate(lines, 1):
        if "<img" in line and "style=" not in line:
            rep.err("R6", "<img> 缺 style，微信会按原尺寸撑破", idx)

    # R7 标签闭合（粗检 span/p/blockquote/pre/section 计数）
    for tag in ("span", "p", "blockquote", "pre", "section"):
        if re.search(rf"<{tag}[\s>]", html_text) and not re.search(rf"</{tag}>", html_text):
            rep.err("R7", f"<{tag}> 有开无闭", 0)

    # ── WARN ────────────────────────────────────────────────────
    for m in re.finditer(r"<pre[^>]*>", html_text, re.I):
        tag = m.group(0)
        bg = re.search(r"background-color\s*:\s*([^;\"']+)", tag)
        if not bg or bg.group(1).strip().lower() in ("transparent", "#fff", "#ffffff", "white"):
            rep.warn("W1", "代码块没有深色底", html_text.count("\n", 0, m.start()) + 1)

    if re.search(r'<a\s[^>]*href="https?://', html_text, re.I):
        rep.warn("W2", "含外链 <a>；公众号正文点不开，通常要降级成纯文本")

    for idx, line in enumerate(lines, 1):
        if re.search(r"[\u201c\u201d\u2018\u2019]", line):
            rep.warn("W3", "含中文直角引号，公众号里建议换成中文弯引号", idx)
            break

    for m in re.finditer(r"<h2[^>]*>", html_text, re.I):
        if "border-left" not in m.group(0):
            rep.warn("W4", "h2 丢了左侧竖条，这个版式的识别点没了",
                     html_text.count("\n", 0, m.start()) + 1)


def lint_theme(path: str, rep: Report) -> None:
    with open(path, encoding="utf-8") as f:
        theme = json.load(f)
    for key, cfg in theme.items():
        if key.startswith("_"):
            continue
        if not isinstance(cfg, dict) or "style" not in cfg:
            rep.err("R3", f"组件 {key} 缺 style 字段", 0)
            continue
        if BANNED_PROPS.search(cfg["style"]):
            hit = BANNED_PROPS.search(cfg["style"]).group(0)
            rep.err("R4", f"组件 {key} 的 style 含微信不支持的 CSS：{hit}", 0)
        if BANNED_ATTR.search(cfg.get("style", "")):
            rep.err("R3", f"组件 {key} 的 style 里混了 class=/id=", 0)


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号 HTML 校验器（0 ERROR 门槛）")
    ap.add_argument("file", nargs="?", help="待校验的 HTML 文件")
    ap.add_argument("--theme", action="store_true", help="只自检组件库")
    ap.add_argument("--max-warn", type=int, default=0, help="允许的 WARN 条数")
    args = ap.parse_args()

    rep = Report()

    if args.theme or not args.file:
        print("[lint-theme] 自检组件库")
        lint_theme(THEME_PATH, rep)
    else:
        if not os.path.exists(args.file):
            print(f"找不到文件：{args.file}", file=sys.stderr)
            return 1
        with open(args.file, encoding="utf-8") as f:
            validate(f.read(), rep)

    for e in rep.errors:
        print(f"  ERROR {e}")
    for w in rep.warnings:
        print(f"  WARN  {w}")

    total_e, total_w = len(rep.errors), len(rep.warnings)
    limit_w = args.max_warn if not args.theme else 0
    print(f"\nERROR {total_e} / WARN {total_w}（允许 WARN <= {limit_w}）")

    if total_e > 0:
        print("结果：不通过。ERROR 必须 0，先修再发。")
        return 1
    if total_w > limit_w:
        print("结果：不通过。WARN 超阈值。")
        return 1
    print("结果：通过。可以复制到公众号。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
