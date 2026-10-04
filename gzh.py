#!/usr/bin/env python3
"""
公众号排版一条龙 —— 项目统一入口。

四段闭环：
  extract  别人的文章  → 排版参数（my-styles/*.json）
  theme    排版参数    → 可渲染主题（themes/*.json）
  render   Markdown    → 微信可用全内联样式 HTML
  validate  HTML       → 0 ERROR 门槛校验

用法:
  python3 gzh.py list                          # 列出所有可用主题
  python3 gzh.py extract <公众号链接>           # 提取并归档到 my-styles/
  python3 gzh.py theme "my-styles/*.json"      # 批量转成主题
  python3 gzh.py diff <a.json> <b.json>        # 两份排版参数逐项比，看差在哪
  python3 gzh.py render <文章.md> --theme 技术类 --preview
  python3 gzh.py build  <文章.md> --theme 技术类   # 渲染+预览页+校验（推荐）
  python3 gzh.py validate <文章.html>
  python3 gzh.py public                        # 重新生成脱敏公开版（themes-public/）
  python3 gzh.py public --check                # 只体检：公开版有没有残留原文信息

退出码: 0 通过 / 1 失败（校验不通过时 build 会返回 1）
"""

import argparse
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

VALIDATE = os.path.join(HERE, "validate_gzh_html.py")


def run(args: list[str], desc: str = "") -> bool:
    # flush=True：重定向到管道时 print 是块缓冲的，不 flush 会让这一行
    # 排到子进程输出后面（体检时看着像「结果先出、标题后出」）
    print(f"── {desc or ' '.join(args[:2])}", flush=True)
    r = subprocess.run([sys.executable] + args, cwd=HERE)
    if r.returncode != 0:
        print(f"   ✗ 失败：{' '.join(args[:2])}", flush=True)
    return r.returncode == 0


# ─── extract：抓别人的文章，取排版参数 ───────────────────────────
def cmd_extract(args) -> int:
    import gzh_extract

    try:
        result = gzh_extract.extract(args.url)
    except (gzh_extract.FetchError, gzh_extract.ArticleError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    os.makedirs(os.path.join(HERE, "my-styles"), exist_ok=True)
    name = args.name or (args.type + "_" if args.type else "") + "article"
    path = os.path.join(HERE, "my-styles", f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✓ 已归档：my-styles/{name}.json")
    if args.theme:
        run([os.path.join(HERE, "style_to_theme.py"), path], "顺手转成主题")
    return 0


# ─── diff：两份排版参数逐项对比 ─────────────────────────────────
def cmd_diff(args) -> int:
    def flatten(path: str) -> dict:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        merged = {t["label"]: t.get("value", "") for t in d.get("tokens", [])}
        merged.update({f"基准-{k}": v for k, v in (d.get("baseStyle") or {}).items()})
        for key in ("headingCount", "quoteCount", "separatorCount", "cardCount", "imageCount"):
            if key in d:
                merged[f"数量-{key}"] = d[key]
        return merged

    try:
        left, right = flatten(args.a), flatten(args.b)
    except (OSError, ValueError) as exc:
        print(f"✗ 读不了：{exc}", file=sys.stderr)
        return 1

    keys = sorted(set(left) | set(right))
    print(f"{'参数':<18}{os.path.basename(args.a):<24}{os.path.basename(args.b):<24}差异")
    print("-" * 78)
    same = 0
    for key in keys:
        a, b = left.get(key, "—"), right.get(key, "—")
        if a == b:
            same += 1
        print(f"{key:<18}{str(a):<24}{str(b):<24}{'' if a == b else '≠'}")
    print("-" * 78)
    print(f"{len(keys) - same}/{len(keys)} 项不同")
    return 0


# ─── pipeline：提取 → 主题 → 渲染 → 校验 ────────────────────────
def cmd_pipeline(args) -> int:
    src = os.path.join(HERE, "my-styles", f"{args.name or 'refer'}.json")
    if not os.path.exists(src):
        # 先提取
        a = argparse.Namespace(url=args.url, name=args.name, type=args.type, theme=False)
        if cmd_extract(a) != 0:
            return 1

    if not run([os.path.join(HERE, "style_to_theme.py"), src], f"生成主题（{args.name or 'refer'}）"):
        return 1

    theme = args.name or "refer"
    return cmd_render(argparse.Namespace(md=args.md, out=args.out, preview=True,
                                         title=args.title, theme=theme, validate=True))


def cmd_render(args) -> int:
    out = args.out
    name = args.title or os.path.splitext(os.path.basename(args.md))[0]
    cmd = [os.path.join(HERE, "wechat_render.py"), args.md, "--preview",
           "--title", name]
    if getattr(args, "theme", ""):
        cmd += ["--theme", args.theme]          # 漏了这句，--theme 会被静默吃掉走默认版式
    if out:
        cmd += ["-o", out]
    r = run(cmd, "渲染")
    if not r:
        return 1
    html = out or os.path.splitext(args.md)[0] + ".html"
    if args.validate:
        return 0 if run([VALIDATE, html], "校验") else 1
    return 0


def cmd_validate(args) -> int:
    return 0 if run([VALIDATE, args.html], "校验") else 1


def cmd_list(_) -> int:
    from wechat_render import list_themes
    themes = list_themes()
    print("可用主题（--theme 取值）：")
    print("  (默认)  local-theme.json   绿竖条 + 677px 白底 + 深色代码块")
    for t in themes:
        p = os.path.join(HERE, "themes", t + ".json")
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            accent = d.get("_accent", "")
            from_t = (d.get("_from", {}) or {}).get("title", "")
            print(f"  {t:<20} accent={accent}   学自：{from_t[:28]}")
        except Exception as e:
            print(f"  {t:<20} (读取失败：{e})")
    return 0


def cmd_public(args) -> int:
    script = os.path.join(HERE, "desensitize.py")
    argv = [script, "--check"] if args.check else [script]
    return 0 if run(argv, "脱敏公开版体检" if args.check else "生成脱敏公开版") else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="公众号排版一条龙", prog="gzh.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出所有主题")

    p = sub.add_parser("extract", help="提取参考文章的排版参数")
    p.add_argument("url")
    p.add_argument("--name", default="", help="存档名（默认 article）")
    p.add_argument("--type", default="", help="文章类型前缀，如 技术类")
    p.add_argument("--theme", action="store_true", help="提取完直接转主题")

    p = sub.add_parser("theme", help="把提取的参数转成可渲染主题")
    p.add_argument("styles", nargs="+")

    p = sub.add_parser("render", help="Markdown → 微信 HTML")
    p.add_argument("md")
    p.add_argument("-o", "--out", default=None)
    p.add_argument("--preview", action="store_true")
    p.add_argument("--title", default="")
    p.add_argument("--theme", default="")
    p.add_argument("--validate", action="store_true", help="渲染完顺手校验")

    p = sub.add_parser("validate", help="校验 HTML")
    p.add_argument("html")

    p = sub.add_parser("build", help="渲染 + 预览页 + 校验（推荐）")
    p.add_argument("md")
    p.add_argument("-o", "--out", default=None)
    p.add_argument("--title", default="")
    p.add_argument("--theme", default="")

    p = sub.add_parser("diff", help="对比两份排版参数")
    p.add_argument("a")
    p.add_argument("b")

    p = sub.add_parser("public", help="生成 / 体检脱敏公开版")
    p.add_argument("--check", action="store_true", help="只体检不重新生成")

    p = sub.add_parser("pipeline", help="提取 → 主题 → 渲染 → 校验")
    p.add_argument("url", help="参考的文章链接")
    p.add_argument("md", help="要排版的自己的 Markdown")
    p.add_argument("--name", default="", help="参考存档名，默认 refer")
    p.add_argument("--type", default="")
    p.add_argument("-o", "--out", default=None)
    p.add_argument("--title", default="")

    args = ap.parse_args()

    if args.cmd == "theme":
        return 0 if run([os.path.join(HERE, "style_to_theme.py")] + args.styles, "生成主题") else 1
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "render":
        return cmd_render(args)
    if args.cmd == "extract":
        return cmd_extract(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    if args.cmd == "build":
        return cmd_render(argparse.Namespace(md=args.md, out=args.out, preview=True,
                                             title=args.title, theme=args.theme,
                                             validate=True))
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "public":
        return cmd_public(args)
    return cmd_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
