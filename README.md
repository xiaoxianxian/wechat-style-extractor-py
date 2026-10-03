# gzh typeset —— 公众号排版本地闭环

一条命令把 Markdown 排成能直接粘进微信公众号的 HTML，**全程在本地跑，不联网、不调 API、不花钱**。

别人做排版工具是「给你一套内置模板，你自己选」；这个做的是「先看一篇好文章怎么排的，把它的排版 DNA 学过来，变成你自己的主题」。前者是查表，后者是抄作业——抄完还是你的。

---

## 四段闭环

```
extract   别人的文章 → 排版参数          my-styles/*.json
   ↓
theme     排版参数   → 可渲染主题        themes/*.json
   ↓
render    Markdown   → 全内联样式 HTML   xxx.html
   ↓
validate  HTML       → 0 ERROR 门槛     校验不通过就不许发
```

| 阶段 | 脚本 | 干什么 |
|---|---|---|
| extract | `gzh_extract.py` | 抓公众号文章，反提强调色 / 正文字号 / 行高 / 用了哪些组件 |
| theme | `style_to_theme.py` | **关键一步**：把提取到的参数转成可渲染主题，并在白底上做对比度校验 |
| render | `wechat_render.py` | Markdown → 微信可用 HTML（样式全部内联，文字节点全包 `<span>`） |
| validate | `validate_gzh_html.py` | 7 条 ERROR 规则，0 ERROR 才让发 |
| 编排 | `gzh.py` | 上面四段的一条龙入口 |

---

## 快开始

```bash
cd wechat-style-extractor-py

# 1. 看有哪些主题
python3 gzh.py list

# 2. 排一篇文章（默认用老板自有版式：绿竖条 + 677px 白底 + 深色代码块）
python3 gzh.py build 文章.md --title "文章标题"

# 3. 换个风格：从一篇参考文章学来的主题
python3 gzh.py build 文章.md --title "文章标题" --theme Harness类

# 4. 全链路：抓参考文章 → 学它的排版 → 用它的风格排我这篇
python3 gzh.py pipeline "https://mp.weixin.qq.com/s/xxx" 我的文章.md

# 5. 两份存档比一比，看别人和我的排版差在哪
python3 gzh.py diff my-styles/技术类.json my-styles/部署类.json
```

`build` 会一次产出：正文 `文章.html` + 带「复制到公众号」按钮的预览页 `文章-preview.html`，跑完校验 0 ERROR 才算过。

---

## 主题从哪来

两个来源：

1. **自有的**（`components/local-theme.json`）——绿竖条 H2、677px 白底、深色代码块。改这里就改全局，别去改渲染器。
2. **学来的**（`themes/*.json`）——从 `my-styles/` 里的排版参数生成。

### 为什么学来的必须过一道转换

提取器抓到的色值是**别人的底色上的**。别人的正文色可能是浅灰（他底是黑的），照搬到你白底文章上就是一片糊。`style_to_theme.py` 干的就是这件事：

| 原色（别人的） | 转换后（你的白底） | 原因 |
|---|---|---|
| 强调色 `#C678DD` | `#C476DA` | 白底上对比度不够，往深压到 3:1 |
| 正文色 `#ABB2BF` | `#2B2B2B` | 浅色正文在白底不可读，直接兜底深色 |
| 卡片底色 `#282C34` | `#F5F5F5` | 深色面板套白底会闷，亮化 |

被改前的原色都记在主题文件的 `_originalColors` 里，改坏了能还原。

```bash
python3 style_to_theme.py "my-styles/*.json"     # 批量学
python3 style_to_theme.py my-styles/技术类.json -o themes/我的主题.json
```

---

## Markdown 支持

| 语法 | 产出 |
|---|---|
| `#` `##` `###` `####` | 标题，`##` 是绿竖条 |
| 普通段落 | 正文段 |
| `**粗体**` `*斜体*` `` `代码` `` | 行内，全部带 span |
| `- 项` / `1. 项` | 无序 / 有序列表 |
| `> 引用` | 引用块 |
| `!!! 提示 !!!` | **重点提示框**（从参考文章学来的组件） |
| ` ```代码块``` ` | 深色代码块 |
| `![图注](url)` | 图片 + 居中图注 |
| `---` | 分割线 |

---

## 校验规则（0 ERROR 门槛）

公众号编辑器会静默过滤掉某些写法，出问题时你根本看不出哪里错。所以渲染完强制校验：

| 编号 | 规则 | 不干的后果 |
|---|---|---|
| R1 | 禁 `<div>` | 编辑器解析错乱 |
| R2 | 禁 `<style>`/`<script>`/`<link>`/`<iframe>` | 直接被剥掉 |
| R3 | 禁 `class=` / `id=` | 样式全丢 |
| R4 | 禁 `position`/`float`/`display:flex`/`grid` | 手机端排版塌 |
| R5 | 文字节点必须包 `<span>` | 编辑器重写裸文本，样式掉一半 |
| R6 | 必须包在 `<section>` 容器里 | 宽度失控 |
| R7 | 链接必须带 `http` | 微信会自动加壳 |

```bash
python3 validate_gzh_html.py 文章.html          # 0 ERROR 才算过
python3 validate_gzh_html.py 文章.html --max-warn 2   # 允许 2 条 WARN
python3 validate_gzh_html.py --theme            # 只自检组件库
```

校验器反向测过：故意写脏 HTML，6 ERROR + 3 WARN 全抓到、退出码 1——是真门槛，不是摆设。

---

## 目录结构

```
# 公开树（可推远程）
gzh.py                        一条龙入口
gzh_extract.py                提取层：抓文章 → 排版参数（自写，纯标准库）
style_to_theme.py             参数 → 主题（含对比度转换）
wechat_render.py              Markdown → 内联样式 HTML
validate_gzh_html.py          0 ERROR 校验器
desensitize.py                脱敏：生成 / 体检公开版
components/local-theme.json   自有版式组件库（改这里改全局）
themes-public/*.json          脱敏后的可渲染主题
my-styles-public/*.json       脱敏后的排版参数存档
example-article*.md/html      示例产物

# 内部（.gitignore 已排除，不进公开树）
themes/ my-styles/            带原文身份信息的原版
_legacy/                      来源不明的原件 + 溯源档案
_internal/                    跨 agent 项目记忆
```

纯标准库，零依赖，`python3` 直接跑。

---

## 关于「TierFlow-Design」这类外部排版技能

同类开源技能（如 TierFlow-Design）的做法是：**内置一套固定组件库，装配生成**。这套东西的思路值得抄的是「组件库 + 校验 + 0 ERROR 门槛」这个结构，但组件本身要自己写。

这里没复制任何一个外部组件。区别在定位：

- 外部技能 → 内置固定模板，谁用都一样
- 这里 → **从参考文章学排版、做可读性转换、再变你自己的主题**

固定模板谁都能拿，学来的风格不是。

---

## ⚠️ 来源与协议（2026-10-04 已决策：提取层自写清干净）

**公开树里的东西全部为本项目原创**：`README.md`、`gzh.py`、`gzh_extract.py`、`style_to_theme.py`、
`wechat_render.py`、`validate_gzh_html.py`、`desensitize.py`、`components/`、
`themes-public/`、`my-styles-public/`、`example-article*`。没有任何一行来自外部项目。

**原本的提取脚本**（`wechat_style_extractor.py`、`server.py`、`compare_styles.py`、`batch_polish.py`、
`wechat_polisher.py` 及若干 shell 脚本）来自网络，**当时目录里没有它们的 LICENSE 与出处**。
2026-10-04 用四组代码特征（`wechat_style_extractor`/`is_accent_color`/`pixel_value`/`build_result`）
做 GitHub 公开代码搜索，没命中同源仓库；同名的 `sennkuwu/wechat-style-extractor` 是 Next.js + TypeScript 版，
`IT-Althusser/wechat-writer-skills` 的 `learn_theme.py` 是 BeautifulSoup + YAML 版，都不是这一份 Python 版。

没标注许可证的代码，法律上默认「保留所有权利」。owner 在「溯源补署名」和「自写替换」之间选了后者：
`gzh_extract.py` 是完整重写的提取层（纯标准库），**输出结构与旧版同构**，所以已有的
`my-styles/*.json` 一行都不用改就能接着用。原件连同全部原始文件封存在 `_legacy/`，**不进公开树**，
溯源线索写在 `_legacy/README.md` 里。

### 哪些目录不公开

| 目录 | 装的是什么 | 处理 |
|---|---|---|
| `_legacy/` | 来源不明的原件 + 溯源档案 | 已归档，`.gitignore` 排除 |
| `_internal/` | 跨 agent 的项目记忆 | 同上 |
| `themes/`、`my-styles/` | 带原文标题 / 公众号名 / 文章链接 | 同上 |

原文照留——自己日后想回头看「当初那篇到底长什么样」时还得用。但另有脱敏版进公开树。

### 脱敏怎么做的

`desensitize.py` 是**确定性变换**（不是手改一遍），以后新提一个主题再跑一次就自动带上：

```bash
python3 gzh.py public          # 重新生成 themes-public/ 与 my-styles-public/
python3 gzh.py public --check  # 只体检：公开版里还有没有原文身份残留
```

只删身份（原文标题 / 公众号名 / 文章链接），不删排版能力（色值、字号、行高、段距、组件计数全留）。
体检查三类：URL、已知身份字段、以及「≥8 个连续中文」这种疑似漏出的长标题。

反向验证过：往公开版里塞一条链接、再塞一条 10 字以内的中文标题，`--check` 两样都报得出来、退出码 1。

---

## 已知限制

- 微信新版编辑器里 `#js_name` 常拿不到，此时回退读 `<meta name="author">`，都拿不到就填「公众号作者」。
- 有些文章的颜色写在非元素 style 上（外层 section 或内联 class），提取器抓不到时主题会回落到自有版式配色，不影响出稿。
- 提取层只接受 `mp.weixin.qq.com` 的 https 链接，返回验证页时会明确报错（说明被限流了，换篇或等会儿）。
