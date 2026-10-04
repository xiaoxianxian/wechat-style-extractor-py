#!/usr/bin/env python3
"""
本地公众号版式渲染器 —— 把 Markdown 渲染成微信可用（全内联样式）的 HTML。

用法:
  python3 wechat_render.py 输入.md [-o 输出.html] [--preview] [--title "文章标题"]

输出:
  -o 指定路径时写该文件，否则写 输入.html（同名同目录）
  --preview 时另生成 输出-preview.html（带「复制到公众号」按钮的预览页）

设计约定:
  1. 样式只从 components/local-theme.json 取，渲染器不自带任何颜色/字号。
     换主题 = 改 JSON，不用改代码。
  2. 所有文字节点包在 <span style="..."> 里 —— 微信编辑器会重写未包裹的裸文本。
  3. 不用 <div>/class/id/position/float/display:flex —— 微信过滤或错乱。
  4. 渲染完必须跑 validate_gzh_html.py，ERROR 数必须 0。
"""

import argparse
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_THEME = os.path.join(HERE, "components", "local-theme.json")


# ─── 主题 ────────────────────────────────────────────────────────
def theme_dirs() -> list[str]:
    """主题搜索目录，按优先级：内部 themes/（带原文身份，.gitignore 排除）→ 公开 themes-public/。

    两个都要扫——themes/ 不进公开树，只认它的话，clone 下来的人 --theme 任何主题都会
    「找不到主题」然后 build 直接失败。
    """
    return [os.path.join(HERE, "themes"), os.path.join(HERE, "themes-public")]


def resolve_theme(name: str = "") -> str:
    """空 = 默认主题（components/local-theme.json）；否则先当路径，再按目录顺序找。"""
    if not name:
        return DEFAULT_THEME
    if os.path.isfile(name):
        return name
    for d in theme_dirs():
        p = os.path.join(d, name if name.endswith(".json") else name + ".json")
        if os.path.isfile(p):
            return p
    raise SystemExit(f"找不到主题：{name}\n已可用的主题：{', '.join(list_themes()) or '（空）'}")


def list_themes() -> list[str]:
    names: set[str] = set()
    for d in theme_dirs():
        if os.path.isdir(d):
            names |= {f[:-5] for f in os.listdir(d) if f.endswith(".json")}
    return sorted(names)


def load_theme(path: str = DEFAULT_THEME) -> dict:
    if not os.path.exists(path):
        raise SystemExit(f"找不到主题文件：{path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ─── 行内标记 ────────────────────────────────────────────────────
INLINE_RE = re.compile(
    r"(`[^`]+`)"          # 1 行内代码
    r"|(\*\*[^*]+\*\*)"   # 2 粗体
    r"|(\*[^*]+\*)"       # 3 斜体
    r"|(\[[^\]]+\]\([^)]+\))"  # 4 链接
)


def render_inline(text: str, theme: dict) -> str:
    """把行内标记转成带内联样式的 span/code。链接在公众号会被过滤，降级成纯文本。"""
    strong = theme.get("strong", {})
    em = theme.get("em", {})
    link = theme.get("link", {})
    inline_code = theme.get("inlinecode", {})

    def _tag(kind: str, body: str) -> str:
        if kind == "code":
            st = inline_code.get("style", "")
            return f'<code style="{st}"><span style="{st}">{body}</span></code>'
        cfg = strong if kind == "strong" else (em if kind == "em" else link)
        st = cfg.get("style", "")
        return f'<span style="{st}">{body}</span>'

    out = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        pos = m.end()
        tok = m.group(0)
        if tok.startswith("`") and tok.endswith("`") and len(tok) > 1:
            out.append(_tag("code", html.escape(tok[1:-1])))
        elif tok.startswith("**") and tok.endswith("**"):
            out.append(_tag("strong", html.escape(tok[2:-2])))
        elif tok.startswith("*") and tok.endswith("*") and len(tok) > 2:
            out.append(_tag("em", html.escape(tok[1:-1])))
        else:
            label = tok.split("]")[0][1:]
            out.append(_tag("link", html.escape(label)))
    out.append(html.escape(text[pos:]))
    return "".join(out)


# ─── 块级渲染 ────────────────────────────────────────────────────
def wrap_span(inner: str, style: str) -> str:
    """文字节点一律包 span —— 这是微信兼容的关键，不是可选项。"""
    return f'<span style="{style}">{inner}</span>'


IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,})\s*$")
UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
H_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def render_markdown(md_text: str, theme: dict, title: str = "") -> str:
    lines = md_text.replace("\r\n", "\n").split("\n")
    c = theme
    body: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # 代码块
        if line.strip().startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            pre = c.get("codeblock", {})
            inner = c.get("codeblock", {}).get("innerStyle", "")
            code = html.escape("\n".join(buf))
            body.append(f'<pre style="{pre.get("style","")}">'
                        f'<code style="{inner}"><span style="{inner}">'
                        f'{code}</span></code></pre>')
            continue

        # 空行
        if not line.strip():
            i += 1
            continue

        # 标题
        m = H_RE.match(line)
        if m:
            level = min(len(m.group(1)), 4)
            key = f"h{level}"
            cfg = c.get(key, c.get("h2", {}))
            deco = cfg.get("decoration", "")
            style = cfg.get("style", "") + deco
            tag = cfg.get("tag", "h2")
            body.append(f'<{tag} style="{style}">'
                        f'{wrap_span(render_inline(m.group(2), theme), style)}</{tag}>')
            i += 1
            continue

        # 分割线
        if HR_RE.match(line):
            hr = c.get("hr", {})
            body.append(f'<hr style="{hr.get("style","")}" />')
            i += 1
            continue

        # 图片
        if IMG_RE.search(line):
            for alt, src in IMG_RE.findall(line):
                img = c.get("image", {})
                body.append(f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" '
                            f'style="{img.get("style","")}" />')
                if alt:
                    cap = c.get("caption", {})
                    body.append(f'<p style="{cap.get("style","")}">'
                                f'{wrap_span(html.escape(alt), cap.get("style",""))}</p>')
            i += 1
            continue

        # 提示框 !!! 内容 !!!  —— 对应参考文章里的「重点提示」组件
        if line.strip().startswith("!!!"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("!!!"):
                if lines[i].strip():
                    buf.append(lines[i])
                i += 1
            i += 1
            cfg = c.get("callout") or c.get("blockquote", {})
            qstyle = cfg.get("style", "")
            inner = "\n".join(render_inline(x, theme) for x in buf)
            body.append(f'<blockquote style="{qstyle}">'
                        f'{wrap_span(inner, qstyle)}</blockquote>')
            continue

        # 引用
        if line.strip().startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            q = c.get("blockquote", {})
            qstyle = q.get("style", "")
            inner = "\n".join(render_inline(x, theme) for x in buf if x.strip())
            body.append(f'<blockquote style="{qstyle}">'
                        f'{wrap_span(inner, qstyle)}</blockquote>')
            continue

        # 列表
        if UL_RE.match(line) or OL_RE.match(line):
            ordered = OL_RE.match(line) is not None
            tag = c.get("ol" if ordered else "ul", {}).get("tag", "ol" if ordered else "ul")
            lstyle = c.get("ol" if ordered else "ul", {}).get("style", "")
            listype = "decimal" if ordered else "disc"
            lstyle = re.sub(r"list-style-type:[^;]*;?", "", lstyle)
            items = []
            while i < n:
                m = OL_RE.match(lines[i]) if ordered else UL_RE.match(lines[i])
                if not m:
                    break
                istyle = c.get("li", {}).get("style", "")
                items.append(f'<li style="{istyle}">'
                             f'{wrap_span(render_inline(m.group(1), theme), istyle)}</li>')
                i += 1
            body.append(f'<{tag} style="{lstyle}list-style-type:{listype};">' + "".join(items) + f'</{tag}>')
            continue

        # 正文段落
        buf = []
        while i < n and lines[i].strip() and not (
            H_RE.match(lines[i]) or HR_RE.match(lines[i])
            or lines[i].strip().startswith(">")
            or IMG_RE.search(lines[i])
            or UL_RE.match(lines[i]) or OL_RE.match(lines[i])
            or lines[i].strip().startswith("```")
        ):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            p = c.get("p", {})
            pstyle = p.get("style", "")
            inner = render_inline(" ".join(buf), theme)
            body.append(f'<p style="{pstyle}">{wrap_span(inner, pstyle)}</p>')

    container = c.get("container", {})
    cstyle = container.get("style", "")
    return f'<section style="{cstyle}">\n' + "\n".join(body) + "\n</section>"


# ─── 预览页（带「复制到公众号」按钮）──────────────────────────────
PREVIEW_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>
  body {{ margin:0; padding:24px 12px 60px; background:#EDEDED; font-family:-apple-system,'PingFang SC',sans-serif; }}
  .bar {{ position:sticky; top:0; z-index:9; background:#fff; border:1px solid #DCDCDC;
          border-radius:8px; padding:12px 14px; margin:0 auto 18px; max-width:677px;
          display:flex; gap:10px; align-items:center; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
  .bar button {{ border:0; border-radius:6px; background:#1F8A5C; color:#fff; font-size:14px;
                 padding:8px 16px; cursor:pointer; }}
  .bar button.ghost {{ background:#F2F4F3; color:#3A3A3A; }}
  .bar span.tip {{ font-size:12px; color:#8A8A8A; }}
  .paper {{ max-width:677px; margin:0 auto; background:#fff; border-radius:8px;
            padding:28px 20px; box-sizing:border-box; }}
  @media (max-width:700px) {{ .paper {{ padding:18px 14px; }} }}
</style>
</head>
<body>
<div class="bar">
  <button id="copyBtn" type="button">复制到公众号</button>
  <button id="srcBtn" class="ghost" type="button">看源码</button>
  <span class="tip">复制后到公众号编辑器粘贴即可，记得检查图片与表格</span>
</div>
<div class="paper" id="paper">{body}</div>
<script>
var src = {src_json};
document.getElementById('srcBtn').onclick = function () {{
  var p = document.getElementById('paper');
  p.innerHTML = '<pre style="white-space:pre-wrap;font-size:12px;">' + src + '</pre>';
}};
document.getElementById('copyBtn').onclick = function () {{
  var btn = this, old = '复制到公众号';
  var done = function (ok) {{
    btn.textContent = ok ? '已复制，去粘贴' : '复制失败，请手动选中';
    setTimeout(function () {{ btn.textContent = old; }}, 2000);
  }};
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(src).then(function () {{ done(true); }},
                                          function () {{ done(false); }});
  }} else {{
    var ta = document.createElement('textarea');
    ta.value = src; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    var ok = false; try {{ ok = document.execCommand('copy'); }} catch (e) {{}}
    document.body.removeChild(ta); done(ok);
  }}
}};
</script>
</body>
</html>
"""


def build_preview(body_html: str, src_html: str, title: str = "公众号排版预览") -> str:
    return PREVIEW_TPL.format(
        title=html.escape(title),
        body=body_html,
        src_json=json.dumps(src_html, ensure_ascii=False),
    )


# ─── CLI ─────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown → 微信可用内联样式 HTML")
    ap.add_argument("md", help="输入的 Markdown 文件")
    ap.add_argument("-o", "--out", help="输出 HTML 路径，默认与输入同目录同名")
    ap.add_argument("--preview", action="store_true", help="额外生成带复制按钮的预览页")
    ap.add_argument("--title", default="", help="文章标题（仅用于预览页 <title>）")
    ap.add_argument("--theme", default="", help=f"主题名（themes/ 下），默认自有版式。可用：{', '.join(list_themes()) or '（暂无）'}")
    args = ap.parse_args()

    theme = load_theme(resolve_theme(args.theme))
    with open(args.md, encoding="utf-8") as f:
        md_text = f.read()

    body = render_markdown(md_text, theme, args.title)
    out = args.out or os.path.splitext(args.md)[0] + ".html"

    with open(out, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"[render] 正文 HTML -> {out}")

    if args.preview:
        pv = os.path.splitext(out)[0] + "-preview.html"
        with open(pv, "w", encoding="utf-8") as f:
            f.write(build_preview(body, body, args.title or os.path.basename(args.md)))
        print(f"[render] 预览页     -> {pv}")

    print(f"[render] 请接着跑：python3 validate_gzh_html.py {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
