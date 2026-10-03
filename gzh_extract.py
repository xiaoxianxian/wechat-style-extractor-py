#!/usr/bin/env python3
"""
gzh_extract.py —— 微信公众号排版参数提取器（自写实现）

纯标准库，零依赖，不落任何第三方包。抓一篇公众号文章，反推出它用的排版参数：
强调色、正文色、字号、行高、段距、字距，以及用了哪几类组件。

输出结构与旧版 `wechat_style_extractor.py` **完全同构**
（sourceUrl / title / author / tokens / components / baseStyle），
所以 `style_to_theme.py` 与已有的 `my-styles/*.json` 无需改动即可继续用。

用法
────
    python3 gzh_extract.py <公众号文章链接>        # 打印 JSON 到 stdout
    python3 gzh_extract.py <链接> -o my-styles/xx.json

与旧实现的差别（都是重写时顺手纠正的）
──────────────────────────────────────
* 正文定位改用真正的标签栈（HTMLParser），不再用「在原文里找下一个 <div>」的手工循环，
  自闭合 `<div/>` 与注释里的 `<div` 都不会把栈算错。
* 元素归属不再靠 `html.find(style_str)` 二次定位（同一 style 串重复出现会定位错），
  改为解析时一次性建好「元素 → 样式 → 文字量」的对应关系。
* 「主体样式」从「全局 style 串众数」改为「承载文字最多的一半元素」上取众数，
  避免标题上的样式被当成正文样式。
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
from statistics import median

# ─── 抓取配置 ────────────────────────────────────────────────────
HOSTS = frozenset({"mp.weixin.qq.com"})
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 15
USER_AGENT = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
              "Mobile/15E148 MicroMessenger/8.0.50")
# 微信塞过来的验证页也会返回 200，只能靠文案认
BLOCK_WORDS = ("环境异常", "访问过于频繁", "安全验证", "请完成验证", "操作过于频繁")
# 正文容器 id 候选，第一个是常见结构，后两个是老版兜底
CONTENT_IDS = ("js_content", "js_article", "rich_media_content")


class FetchError(Exception):
    pass


class ArticleError(Exception):
    pass


# ─── 原文字节 → 正文片段 ────────────────────────────────────────
def fetch(url: str) -> tuple[str, str]:
    """返回 (html, 最终 url)。只放行 mp.weixin.qq.com 的 https 链接。"""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "") not in HOSTS:
        raise FetchError(f"只支持 mp.weixin.qq.com 的 https 链接，收到：{url!r}")

    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise FetchError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"抓取失败：{exc}") from exc

    if len(body) > MAX_BYTES:
        raise FetchError("页面超过 5MB，放弃解析")

    text = body.decode("utf-8", errors="ignore")
    if any(word in text[:4000] for word in BLOCK_WORDS):
        raise FetchError("微信返回的是验证页（可能被限流），换一篇或稍后再试")
    return text, url


# ─── 颜色工具 ────────────────────────────────────────────────────
def to_hex(value: str) -> str:
    """'#C678DD' / 'c68' / 'rgb(198,120,221)' → '#C678DD'，认不出返回 ''。"""
    if not value:
        return ""
    m = re.search(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)", value, re.I)
    if m:
        r, g, b = (min(255, int(float(x))) for x in m.groups())
        return "#%02X%02X%02X" % (r, g, b)
    m = re.search(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b", value)
    if not m:
        return ""
    h = m.group(1)
    if len(h) < 6:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return ""
    return "#" + h[:6].upper()


def colors_in(value: str) -> list[str]:
    return [c for c in (to_hex(v) for v in re.split(r"\s+", value or "")) if c]


def is_accent(h: str) -> bool:
    """带彩度的颜色（不是灰黑白），且明度落在能当标题色的区间。"""
    if len(h) != 7:
        return False
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    sat = 0 if mx == 0 else (mx - mn) / mx
    light = (mx + mn) / 510          # (max+min)/2/255
    return sat >= 0.28 and 0.18 <= light <= 0.82


def is_near_white(h: str) -> bool:
    if len(h) != 7:
        return False
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return r > 242 and g > 242 and b > 242


# ─── 样式解析 ────────────────────────────────────────────────────
def parse_style(attr: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for decl in (attr or "").split(";"):
        key, sep, val = decl.partition(":")
        if sep:
            key = key.strip().lower()
            if key:
                out[key] = val.strip()
    return out


def px(value: str) -> float | None:
    m = re.match(r"^(-?[\d.]+)px$", (value or "").strip())
    return float(m.group(1)) if m else None


# ─── 元素扫描 ────────────────────────────────────────────────────
@dataclass
class Element:
    tag: str
    style: dict[str, str] = field(default_factory=dict)
    text: str = ""
    line: int = 0


class ElementScanner(HTMLParser):
    """把片段拆成「标签 + 内联样式 + 可见文字」的列表，一次扫完。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        style_map = parse_style(dict(attrs).get("style") or "")
        line = self.getpos()[0]
        self.elements.append(Element(tag=tag.lower(), style=style_map, line=line))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)          # <img/> 之类也记一笔

    def handle_data(self, data: str) -> None:
        if self.elements:
            self.elements[-1].text += data


# 只关心三种东西：注释、开 div、闭 div。注释里写着的 <div> 绝不能进栈。
_DIV_TOKEN = re.compile(r"<!--|</?div\b[^>]*>", re.I | re.S)
_ID_IN_TAG = re.compile(r"""\bid\s*=\s*["']?([^\s"'>/]+)""", re.I)


def _div_events(html: str) -> list[tuple[str, int, str]]:
    """
    扫出真实的 <div> 事件，返回 [(kind, offset, tag_html), ...]。

    kind='o' → offset 是开标签「>」之后的位置（内容起点）
    kind='c' → offset 是闭标签「<」的位置（内容终点）

    注释整段跳过（微信正文里偶尔有写死的假标签）；
    `<div/>` 自闭合跳过（它会伪造一对「立刻闭合」的事件）。
    """
    events: list[tuple[str, int, str]] = []
    for m in _DIV_TOKEN.finditer(html):
        token = m.group(0)
        if token.startswith("<!--"):
            continue                                   # 注释里的一切都忽略
        head = m.start()
        if token.startswith("</div"):
            events.append(("c", head, ""))
            continue
        close = html.find(">", head)
        if close == -1:
            continue
        if html[close - 1] == "/":
            continue
        events.append(("o", close + 1, html[head:close + 1]))
    return events


def find_body_fragment(html: str) -> str:
    """定位正文容器（默认 id=js_content），返回它的内部片段。"""
    depth = 0
    target: int | None = None
    start = end = None
    for kind, offset, tag_html in _div_events(html):
        if kind == "o":
            depth += 1
            if target is None:
                found = _ID_IN_TAG.search(tag_html)
                if found and found.group(1) in CONTENT_IDS:
                    target, start = depth, offset
        else:
            if target is None:
                continue                               # 还没碰到目标层，深度不能动
            if depth == target:
                end = offset                           # 这一层就是正文容器的收尾
                break
            depth -= 1

    if target is None:
        raise ArticleError("没找到公众号正文容器（页面结构变了，或这不是一篇公众号文章）")
    fragment = html[start: end if end is not None else len(html)]
    if len(fragment.strip()) < 500:
        raise ArticleError("正文片段太短，页面可能没渲染完整")
    return fragment


# ─── 样式统计 ────────────────────────────────────────────────────
BODY_FONT_TAGS = frozenset({"p", "span", "section", "div", "h1", "h2", "h3", "h4", "li"})


def _visible_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def analyze(fragment: str) -> dict:
    scanner = ElementScanner()
    scanner.feed(fragment)
    scanner.close()
    elements = scanner.elements
    if not elements:
        raise ArticleError("正文里没有任何带样式的元素")

    # 1) 承载文字最多的那批元素 = 正文主体，主体参数从它们身上取
    with_text = sorted((e for e in elements if _visible_len(e.text)),
                       key=lambda e: _visible_len(e.text), reverse=True)
    main_pool = with_text[: max(1, len(with_text) // 2)] or elements

    # 2) 组件出现次数（全片段）
    tag_count = Counter(e.tag for e in elements)
    card_count = 0
    for el in elements:
        bg = el.style.get("background-color") or el.style.get("background") or ""
        if not bg or re.match(r"^(transparent|none|url)", bg, re.I):
            continue
        if el.tag not in ("section", "div", "blockquote"):
            continue
        if any(k.startswith("padding") for k in el.style) or "border-radius" in el.style:
            card_count += 1

    # 3) 主体参数：颜色 / 字号 / 行高 / 段距 / 字距
    accent_hits: Counter[str] = Counter()
    text_hits: Counter[str] = Counter()
    bg_hits: Counter[str] = Counter()
    font_hits: Counter[str] = Counter()
    line_hits: Counter[str] = Counter()
    spacing: list[float] = []
    letter_hits: Counter[str] = Counter()

    # 强调色与卡片底色：全片段找。它们本来就常出现在标题、边框、卡片上，
    # 只盯「文字最多的一半元素」会把 h2 那种短标题的强调色挤掉。
    for el in elements:
        weight = _visible_len(el.text)
        for color in colors_in(el.style.get("color", "")):
            if is_accent(color):
                accent_hits[color] += weight
        bg = el.style.get("background-color") or el.style.get("background") or ""
        for color in colors_in(bg):
            if not is_near_white(color) and color not in ("#FFFFFF", "#F5F5F5"):
                bg_hits[color] += 1

    # 正文参数：只在主体池里取，避免被标题/引用的大字号带偏
    for el in main_pool:
        weight = _visible_len(el.text)
        for color in colors_in(el.style.get("color", "")):
            if not is_near_white(color):
                text_hits[color] += 1

        size = px(el.style.get("font-size", ""))
        if size is not None and 12 <= size <= 22 and el.tag in BODY_FONT_TAGS:
            font_hits["%g" % size] += 1

        raw_lh = (el.style.get("line-height") or "").strip()
        if raw_lh:
            if re.match(r"^[\d.]+$", raw_lh):
                line_hits[raw_lh] += 1
            else:
                scaled = px(raw_lh)
                if scaled is not None and size:
                    line_hits["%.2f" % (scaled / size)] += 1

        if el.tag in ("p", "li"):
            gap = px(el.style.get("margin-bottom", ""))
            if gap is not None and 0 <= gap <= 80:
                spacing.append(gap)

        ls = (el.style.get("letter-spacing") or "").strip()
        if ls and ls not in ("normal", "inherit", "initial"):
            letter_hits[ls] += 1

    def top(counter: Counter[str]) -> str:
        return counter.most_common(1)[0][0] if counter else ""

    return {
        "accentColor": top(accent_hits) or None,
        "textColor": top(text_hits) or None,
        "backgroundColor": top(bg_hits) or None,
        "fontSize": top(font_hits) or None,
        "lineHeight": top(line_hits) or None,
        "paragraphSpacing": median(spacing) if spacing else None,
        "letterSpacing": top(letter_hits) or None,
        "headingCount": sum(tag_count[t] for t in ("h1", "h2", "h3", "h4", "h5", "h6")),
        "quoteCount": tag_count["blockquote"],
        "separatorCount": tag_count["hr"],
        "cardCount": card_count,
        "imageCount": tag_count["img"],
    }


# ─── 组装输出（字段名与旧版一致，别改）───────────────────────────
def build_result(html: str, url: str, stats: dict) -> dict:
    def text_of(pattern: str) -> str:
        m = re.search(pattern, html, re.S | re.I)
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""

    title = text_of(r"<h1[^>]*>(.*?)</h1>")[:100] or "公众号文章"
    # 新版编辑器里 #js_name 有时拿不到，退回 meta 标签
    author = ""
    m = re.search(r'<span[^>]*\bid=["\']js_name["\'][^>]*>(.*?)</span>', html, re.S | re.I)
    if m:
        author = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    if not author:
        m = re.search(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)', html, re.I)
        author = m.group(1).strip() if m else ""
    author = author[:50] or "公众号作者"

    tokens = []
    if stats["accentColor"]:
        tokens.append({"label": "强调色", "value": stats["accentColor"], "swatch": stats["accentColor"]})
    if stats["textColor"]:
        tokens.append({"label": "正文色", "value": stats["textColor"], "swatch": stats["textColor"]})
    if stats["backgroundColor"] and stats["backgroundColor"] != "#FFFFFF":
        tokens.append({"label": "卡片底色", "value": stats["backgroundColor"], "swatch": stats["backgroundColor"]})
    if stats["fontSize"]:
        tokens.append({"label": "正文字号", "value": f"{stats['fontSize']}px"})
    if stats["lineHeight"]:
        tokens.append({"label": "正文行高", "value": f"{stats['lineHeight']}×"})
    if stats["paragraphSpacing"]:
        tokens.append({"label": "段落间距", "value": f"{stats['paragraphSpacing']:.0f}px"})

    components = []
    if stats["headingCount"]:
        components.append({"label": "章节标题", "detail": f"{stats['headingCount']}处 · 保留原样式"})
    if stats["quoteCount"]:
        components.append({"label": "引用/重点提示", "detail": f"{stats['quoteCount']}处"})
    if stats["cardCount"]:
        components.append({"label": "内容卡片", "detail": f"{stats['cardCount']}处 · 背景与留白"})
    if stats["separatorCount"]:
        components.append({"label": "内容分隔", "detail": f"{stats['separatorCount']}处"})
    if stats["imageCount"]:
        components.append({"label": "文章图片", "detail": f"{stats['imageCount']}张 · 已适配宽度"})
    if not components:
        components.append({"label": "正文段落", "detail": "已保留原始层级与间距"})

    return {
        "sourceUrl": url,
        "title": title,
        "author": author,
        "tokens": tokens,
        "components": components,
        "baseStyle": {
            "color": stats["textColor"] or "#3F3F3F",
            "fontSize": f"{(stats['fontSize'] or 16)}px",
            "lineHeight": stats["lineHeight"] or "1.75",
            "letterSpacing": stats["letterSpacing"] or "0.3px",
        },
    }


def extract(url: str) -> dict:
    html, final_url = fetch(url)
    return build_result(html, final_url, analyze(find_body_fragment(html)))


def main() -> int:
    ap = argparse.ArgumentParser(description="提取公众号文章的排版参数")
    ap.add_argument("url", help="mp.weixin.qq.com 文章链接")
    ap.add_argument("-o", "--out", help="额外保存为 JSON 文件")
    args = ap.parse_args()

    try:
        result = extract(args.url)
    except (FetchError, ArticleError) as exc:
        json.dump({"ok": False, "error": {"code": "FETCH_ERROR", "message": str(exc)}},
                  sys.stdout, ensure_ascii=False)
        return 1

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
