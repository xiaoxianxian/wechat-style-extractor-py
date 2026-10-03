#!/usr/bin/env python3
"""
把「从别人的公众号文章提取出来的参数」升格成「可渲染的主题」。

用法:
  python3 style_to_theme.py my-styles/Harness类.json
  python3 style_to_theme.py my-styles/Harness类.json -o themes/harness.json
  python3 style_to_theme.py my-styles/*.json --out-dir themes/     # 批量

为什么需要这一步
────────────────
wechat_style_extractor.py 抓的是「别人文章的排版 DNA」——强调色、正文色、
字号行高、用了哪些组件。但这些是**观察结果**，不是**渲染配置**。
直接拿去渲染你自己的文章会翻车：别人的正文色可能是浅灰（他底是黑的），
你的文章底是白的，套上去就是一片糊。

所以这里做一次「可读性转换」：提取到的色值不是照搬，而是先在白底上验证对比度，
不够就往深色推，推到能读为止。这样别人的版式才是可用的，不是眼.tar.gz

输出的主题与 components/local-theme.json 同构，渲染器可以直接吃。
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FALLBACK_ACCENT = "#1F8A5C"   # 老板自有版式的绿，提取不到强调色时兜底
BODY_FALLBACK = "#2B2B2B"
WHITE = "#FFFFFF"


# ─── 颜色工具 ────────────────────────────────────────────────────
def normalize_hex(value: str) -> str:
    """'#C678DD' / 'rgb(198,120,221)' / 'C678DD' -> '#C678DD'"""
    if not value:
        return ""
    v = value.strip().lstrip("#").upper()
    m = re.match(r"rgb\((\d+)[,\s]+(\d+)[,\s]+(\d+)\)", value.strip(), re.I)
    if m:
        v = "%02X%02X%02X" % tuple(int(g) for g in m.groups())
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return "#" + v if len(v) == 6 else ""


def channel_lum(rgb: tuple[int, int, int]) -> float:
    """sRGB 相对亮度（WCAG 定义）。"""
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def hex_lum(hex_color: str) -> float:
    h = normalize_hex(hex_color).lstrip("#")
    if len(h) != 6:
        return 1.0
    return channel_lum(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))


def hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = normalize_hex(hex_color).lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def contrast_ratio(c1: str, c2: str) -> float:
    l1, l2 = hex_lum(c1), hex_lum(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def ensure_contrast(hex_color: str, bg: str, target: float) -> str:
    """在 bg 底上把前景色压暗或提亮到 target 对比度，改动最小的方向优先。"""
    if contrast_ratio(hex_color, bg) >= target:
        return hex_color
    rgb = hex_rgb(hex_color)
    for anchor in ((0, 0, 0), (255, 255, 255)):   # 先试压黑，再试提亮
        for ratio in (i / 100 for i in range(1, 101)):
            moved = tuple(int(c + (a - c) * ratio) for c, a in zip(rgb, anchor))
            probe = "#%02X%02X%02X" % moved
            if contrast_ratio(probe, bg) >= target:
                return probe
    return hex_color


# ─── 提取结果解析 ────────────────────────────────────────────────
def pick(tokens: list[dict], *keywords: str) -> str:
    """在 tokens 里按 label 关键词找色值。"""
    for t in tokens or []:
        label = t.get("label", "")
        if any(k in label for k in keywords):
            for key in ("swatch", "value"):
                v = normalize_hex(str(t.get(key, "")))
                if v:
                    return v
    return ""


def pick_num(tokens: list[dict], *keywords: str) -> str:
    for t in tokens or []:
        if any(k in t.get("label", "") for k in keywords):
            return str(t.get("value", "")).replace("×", "").strip()
    return ""


# ─── 主题生成 ────────────────────────────────────────────────────
def build_theme(style: dict, name: str = "") -> dict:
    tokens = style.get("tokens", [])
    base = style.get("baseStyle", {}) or {}
    accent_raw = pick(tokens, "强调", "主色", "主题色") or FALLBACK_ACCENT

    # 1) 强调色：竖条 / 标题 / 链接用。必须在白底上够深，否则标题糊掉。
    accent = ensure_contrast(accent_raw, WHITE, target=3.0)

    # 2) 正文色：只在自己足够深时才继承（暗色文章的浅灰正文在白底上不可用）
    body_raw = normalize_hex(str(base.get("color", "")))
    body = body_raw if body_raw and contrast_ratio(body_raw, WHITE) >= 7.0 else BODY_FALLBACK

    # 3) 字号 / 行高：直接继承别人实测值，这是提取器的独有价值
    fs = re.search(r"([\d.]+)px", pick_num(tokens, "字号") or str(base.get("fontSize", "")))
    font_size = fs.group(1) + "px" if fs else "16px"
    lh = re.match(r"([\d.]+)", pick_num(tokens, "行高") or str(base.get("lineHeight", "")))
    line_h = (float(lh.group(1)) if lh else 1.75)
    ls = str(base.get("letterSpacing", "")) or "0.01em"

    # 4) 面板底色（引用 / 卡片）：暗色主题的底在白底上会闷，兜成浅灰
    panel_raw = pick(tokens, "卡片", "背景", "面板")
    panel = panel_raw if panel_raw and hex_lum(panel_raw) > 0.85 else "#F5F5F5"

    family = "-apple-system,BlinkMacSystemFont,'PingFang SC','Helvetica Neue',sans-serif"
    mono = "'SFMono-Regular',Menlo,Consolas,monospace"

    def blk(tag: str, style_str: str, **extra) -> dict:
        d = {"tag": tag, "style": style_str}
        d.update(extra)
        return d

    theme = {
        "_readme": f"由 style_to_theme.py 从参考文章（{style.get('title', '未命名')}）自动生成。"
                   f"色值已在白底上做过对比度校验，不要手改 _accent 之外的色。",
        "_accent": accent,
        "_from": {
            "sourceUrl": style.get("sourceUrl", ""),
            "title": style.get("title", ""),
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        },
        "_originalColors": {   # 留个底，方便以后回头看别人原文长什么样
            "accentRaw": accent_raw, "bodyRaw": body_raw, "panelRaw": panel_raw,
            "note": "下面是提取时套用前的原色，改坏了可以照着还原",
        },

        "container": blk("section",
                         f"max-width:677px;width:100%;margin:0 auto;padding:2px 0;"
                         f"font-size:{font_size};line-height:{line_h};letter-spacing:{ls};"
                         f"color:{body};font-family:{family};background-color:#FFFFFF;text-align:left;"),

        "h1": blk("h1", f"font-size:22px;font-weight:700;color:#1A1A1A;line-height:1.45;"
                        f"margin:34px 0 16px;letter-spacing:0.02em;text-align:center;",
                  wrapSpan=False),

        "h2": blk("h2", f"font-size:19px;font-weight:700;color:{accent};line-height:1.5;"
                        f"margin:32px 0 14px;letter-spacing:0.02em;",
                  decoration=f"border-left:4px solid {accent};padding-left:12px;"),

        "h3": blk("h3", f"font-size:16px;font-weight:700;color:#1A1A1A;line-height:1.55;"
                        f"margin:26px 0 10px;letter-spacing:0.01em;",
                  decoration=f"border-left:3px solid {accent}40;padding-left:10px;"),

        "p": blk("p", f"font-size:{font_size};color:{body};line-height:{line_h};"
                      f"letter-spacing:{ls};margin:0 0 18px;text-align:justify;"),

        # callout：从参考文章里学到的「重点提示框」，带底色和色条
        "callout": blk("blockquote", f"font-size:15px;color:{body};line-height:{line_h};"
                                     f"margin:20px 0;padding:12px 14px;background-color:{panel};"
                                     f"border-radius:4px;border-left:4px solid {accent};"),

        "codeblock": blk("pre",
                         f"margin:20px 0;padding:14px 16px;background-color:#1E1E1E;border-radius:6px;"
                         f"overflow-x:auto;font-family:{mono};font-size:13px;line-height:1.65;"
                         f"color:#E6E6E6;text-align:left;",
                         innerStyle="display:inline-block;min-width:100%;white-space:pre;word-break:break-all;"),

        "inlinecode": blk("code", f"font-family:{mono};font-size:14px;padding:1px 5px;border-radius:3px;"
                                  f"background-color:{panel};color:{accent};"),

        "li": blk("li", f"font-size:{font_size};color:{body};line-height:{line_h};"
                        f"margin:0 0 8px;text-align:justify;"),
        "ul": blk("ul", "margin:14px 0 18px;padding-left:22px;list-style-type:disc;"),
        "ol": blk("ol", "margin:14px 0 18px;padding-left:24px;list-style-type:decimal;"),
        "hr": blk("hr", f"border:none;border-top:1px solid {accent}33;margin:30px 0;"),
        "image": blk("img", "display:block;width:100%;height:auto;margin:18px auto;border-radius:4px;"),
        "caption": blk("p", "font-size:13px;color:#8A8A8A;line-height:1.6;margin:-8px 0 20px;text-align:center;"),
        "strong": blk("span", "font-weight:700;color:#1A1A1A;"),
        "em": blk("span", f"font-style:italic;color:{accent};"),
        "link": blk("span", f"color:{accent};text-decoration:underline;"),
        "signoff": blk("p", "font-size:14px;color:#8A8A8A;line-height:1.7;margin:28px 0 8px;"
                            "padding-top:16px;border-top:1px solid #E4E8E6;text-align:center;"),
    }

    if name:
        theme["_name"] = name
    return theme


def theme_name(style: dict, path: str) -> str:
    """用 my-styles 里的文件名当主题名（那是 owner 自己起的，短且好敲）。"""
    return os.path.splitext(os.path.basename(path))[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="把提取的排版参数转成可渲染主题")
    ap.add_argument("styles", nargs="+", help="my-styles/*.json，支持 glob")
    ap.add_argument("-o", "--out", help="单个输出路径")
    ap.add_argument("--out-dir", default=os.path.join(HERE, "themes"),
                    help="批量输出目录（默认 themes/）")
    args = ap.parse_args()

    files: list[str] = []
    for p in args.styles:
        files.extend(sorted(glob.glob(p, recursive=False)) or [p])
    if not files:
        print("没有匹配到任何样式文件", file=sys.stderr)
        return 1

    os.makedirs(args.out_dir, exist_ok=True)

    for path in files:
        with open(path, encoding="utf-8") as f:
            style = json.load(f)
        name = theme_name(style, path)
        theme = build_theme(style, name)
        out = args.out or os.path.join(args.out_dir, f"{name}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(theme, f, ensure_ascii=False, indent=2)
        print(f"[theme] {os.path.basename(path)} -> {out}  (accent={theme['_accent']})")

    print("\n[theme] 渲染时用：python3 wechat_render.py 文章.md --theme <主题名|路径>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
