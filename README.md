# gzh typeset —— 公众号排版本地闭环

一条命令把 Markdown 排成能直接粘进微信公众号的 HTML。全程本地跑，不联网、不调 API、不花钱。

跟别的排版工具的区别在入口：那类给你一套内置模板，你自己挑；这个先去看一篇好文章是怎么排的，把它的排版参数反提出来，转一道对比度校验，变成你自己的主题。前者是选样式，后者是抄作业，抄完还是你的。

> **最后验证：2026-10-04** · Python 3.13 · 纯标准库零依赖 · 全链路（提取 / 主题 / 渲染 / 校验 / 脱敏）实测通过
> 仓库：`github.com/xiaoxianxian/wechat-style-extractor-py`

---

## 先看这条：你该不该用

| 你的情况 | 该不该用 | 说明 |
|---|---|---|
| 写公众号，讨厌每次手动调样式 | 该用 | 一条命令出 HTML，样式全内联，粘进去就是完事 |
| 已有 Markdown 稿，不想换工具 | 该用 | 标准 Markdown，不改写作习惯 |
| 想要「一键好看」的模板生意 | 别用 | 这个不卖模板，是给你一个从参考文章学排版的管道 |
| 排版要交给团队统一套模板 | 别用 | 主题是个人化的，没有团队共享的中心化配置 |
| 需要在线服务 / 图形界面 | 别用 | 命令行工具，无 Web 界面 |

**跑得起来的环境**：Python 3.8 起（只用 `argparse`/`json`/`re`/`html`/`os`/`glob`/`urllib`），
macOS / Linux / Windows 均可。不用装包，不用虚拟环境，`python3 xxx.py` 直接跑。

---

## 这份文档不适合谁

- **想直接拖个网页进去上传的人**：没有 GUI，全是命令行。
- **不接受「学来的主题要过一道对比度转换」的人**：直接拿别人的色值往白底上套，结果是一片糊。转换这一步是默认的，关不掉（也别关）。
- **只想要一个通用绿色模板的人**：用 `components/local-theme.json` 那种内置模板方案更省事，这个项目的价值不在模板本身。

---

## 四段闭环

```
extract   别人的文章  → 排版参数          my-styles/*.json
   ↓
theme     排版参数    → 可渲染主题        themes/*.json
   ↓
render    Markdown    → 全内联样式 HTML   文章.html
   ↓
validate  HTML        → 0 ERROR 门槛      校验不过就不许发
```

| 阶段 | 脚本 | 干什么 |
|---|---|---|
| extract | `gzh_extract.py` | 抓公众号文章，反提强调色 / 正文字号 / 行高 / 用了哪些组件 |
| theme | `style_to_theme.py` | **关键一步**：把提取到的参数转成可渲染主题，并在白底上做对比度校验 |
| render | `wechat_render.py` | Markdown → 微信可用 HTML（样式全部内联，文字节点全包 `<span>`） |
| validate | `validate_gzh_html.py` | 7 条 ERROR 规则，0 ERROR 才让发 |
| 编排 | `gzh.py` | 上面四段的一条龙入口 |

四段都能单独跑，也能用 `gzh.py` 串起来。**`build` 子命令 = 渲染 + 预览页 + 校验**，日常只用它就行。

---

## 快速开始

### 第 1 步：拿到代码

```bash
git clone https://github.com/xiaoxianxian/wechat-style-extractor-py.git
cd wechat-style-extractor-py
```

### 第 2 步：看有哪些主题

```bash
python3 gzh.py list
```

实测输出（3 个随仓库发布的主题 + 1 个内置默认版式）：

```
可用主题（--theme 取值）：
  (默认)  local-theme.json   绿竖条 + 677px 白底 + 深色代码块
  参考一                  accent=#C476DA   脱敏公开版（无原文来源）
  技术类                  accent=#1F8A5C   脱敏公开版（无原文来源）
  部署类                  accent=#1F8A5C   脱敏公开版（无原文来源）
```

> 随仓库发布的三个主题都在 `themes-public/`，`--theme 参考一` 这一类用法在 clone 下来就能直接跑，不需要你自己提取。

### 第 3 步：排一篇（默认版式）

```bash
python3 gzh.py build example-article.md --title "示例文章"
```

跑完校验 0 ERROR，同时产出两份：

| 产物 | 用途 |
|---|---|
| `example-article.html` | 正文，直接复制进公众号编辑器 |
| `example-article-preview.html` | 带「复制到公众号」按钮的预览页 |

### 第 4 步：换一个主题

```bash
python3 gzh.py build example-article.md --title "示例文章" --theme 参考一
```

**怎么确认主题真的换了**：别看退出码，看产物色值。`参考一` 是紫色 `#C476DA`，默认版式是绿色 `#1F8A5C`。

```bash
grep -c '#C476DA' example-article.html   # 输出 4 就是换成功了
```

> 渲染器在你传了 `--theme` 但找不到同名主题时会直接报错退出，不会静默回落到默认版式。但这个项目历史上有过一次「`--theme` 被静默吃掉」的 bug，排查时以产物色值为准最保险。

### 第 5 步：看两份排版差在哪

```bash
python3 gzh.py diff my-styles-public/技术类.json my-styles-public/部署类.json
```

实测输出（节选）：

```
参数                技术类.json                部署类.json                差异
------------------------------------------------------------------------------
基准-fontSize       15px                    14px                    ≠
基准-lineHeight     1.75                    1.85                    ≠
正文字号              15px                    14px                    ≠
正文行高              —                       1.85×                   ≠
段落间距              24.0px                  —                       ≠
------------------------------------------------------------------------------
6/7 项不同
```

### 全链路：抓参考文章 → 学它的排版 → 排我这篇

```bash
# 一条龙：抓链接里的文章，转成主题，再拿这个主题渲染我的稿子
python3 gzh.py pipeline "https://mp.weixin.qq.com/s/xxx" 我的文章.md --title "我的标题"

# 拆开跑也行
python3 gzh.py extract "https://mp.weixin.qq.com/s/xxx" --type 技术类     # 存到 my-styles/技术类_xxx.json
python3 gzh.py theme "my-styles/技术类_xxx.json"                        # 转成主题
python3 gzh.py build 我的文章.md --title "我的标题" --theme 技术类
```

`extract` 时传 `--theme` 可一步到位（提取完直接转主题）。

---

## 主题从哪来

两个来源：

1. **自带版式**（`components/local-theme.json`）：绿竖条 H2、677px 白底、深色代码块。改这一个文件就改全局，别去动渲染器。
2. **学来的**（`themes/*.json`）：从排版参数生成，随仓库发布的是 `themes-public/` 里的脱敏版。

### 为什么学来的必须过一道转换

提取器抓到的色值是**在别人的底色上量到的**。别人的正文色可能是浅灰（他的底是黑的），照搬到你白底文章上就是一片糊。`style_to_theme.py` 做的就是这个转换：

| 原色（别人的底） | 转换后（你的白底） | 为什么改 |
|---|---|---|
| 强调色 `#C678DD` | `#C476DA` | 白底上对比度不够，往深压到 3:1 |
| 正文色 `#ABB2BF` | `#2B2B2B` | 浅色正文在白底读不了，直接兜底深色 |
| 卡片底色 `#282C34` | `#F5F5F5` | 深色面板套白底会闷，亮化 |

改前的原色都记在主题文件的 `_originalColors` 字段里，改坏了能还原。

> **口径说明**：上表三个色值是 2026-10-04 对随仓库发布的三个主题做的实测值。字号、行高、段距不做「深压」处理，只做数值照搬 —— 这些量在白底上不存在对比度问题，强行调整反而会让排版走样。

```bash
python3 style_to_theme.py "my-styles/*.json"              # 批量学
python3 style_to_theme.py my-styles/技术类.json -o themes/我的主题.json
```

---

## Markdown 支持

| 语法 | 产出 |
|---|---|
| `#` `##` `###` `####` | 标题（`##` 带左侧竖条） |
| 普通段落 | 正文段 |
| `**粗体**` `*斜体*` `` `代码` `` | 行内标记，全部带 span |
| `- 项` / `1. 项` | 无序 / 有序列表 |
| `> 引用` | 引用块 |
| `!!! 提示 !!!` | 重点提示框 |
| ` ```代码块``` ` | 深色代码块 |
| `![图注](url)` | 图片 + 居中图注 |
| `---` | 分割线 |

链接在公众号编辑器会被过滤，渲染时降级成纯文本显示。

---

## 校验规则（0 ERROR 门槛）

微信编辑器会静默过滤掉某些写法，出问题你根本看不出哪里错。所以渲染完强制校验：

| 编号 | 规则 | 不干的后果 |
|---|---|---|
| R1 | 禁 `<div>` | 编辑器解析错乱 |
| R2 | 禁 `<style>`/`<script>`/`<link>`/`<iframe>` | 直接被剥掉 |
| R3 | 禁 `class=` / `id=` | 样式全丢 |
| R4 | 禁 `position`/`float`/`display:flex`/`grid` | 手机端排版塌 |
| R5 | 文字节点必须包 `<span>` | 编辑器重写裸文本，样式掉一半 |
| R6 | `<img>` 必须带 `style` | 图片不显示 |
| R7 | 标签必须闭合（粗检） | 结构错乱 |

WARN 四条（不阻断）：代码块没深色底、含外链、中文直引号、H2 丢了左侧竖条。

```bash
python3 validate_gzh_html.py 文章.html                  # 0 ERROR 才算过
python3 validate_gzh_html.py 文章.html --max-warn 2    # 允许 2 条 WARN
python3 validate_gzh_html.py --theme                   # 只自检组件库
python3 gzh.py validate 文章.html                      # 同上，走入口
```

校验器反向测过：故意写脏 HTML，6 ERROR + 3 WARN 全抓到、退出码 1。是真门槛，不是摆设。

---

## 文档地图

| 文档 | 什么时候看 |
|---|---|
| 本 README | 装怎么用 |
| [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | 跑不通、主题不对、提取抓空的时候 |
| [CHANGELOG.md](./CHANGELOG.md) | 想知道改了什么、哪个版本开始变 |

---

## 目录结构

```
# 随仓库发布
gzh.py                        一条龙入口
gzh_extract.py                提取层：抓文章 → 排版参数（自写，纯标准库）
style_to_theme.py             参数 → 主题（含对比度转换）
wechat_render.py              Markdown → 内联样式 HTML
validate_gzh_html.py          0 ERROR 校验器
desensitize.py                脱敏：生成 / 体检公开版
components/local-theme.json   自带版式组件库（改这里改全局）
themes-public/*.json          随仓库发布的主题（可直接 --theme 用）
my-styles-public/*.json       随仓库发布的排版参数存档
example-article*.md/html      示例产物
README.md  TROUBLESHOOTING.md  CHANGELOG.md

# 本地生成，不进仓库（.gitignore 排除）
themes/ my-styles/           从参考文章提取的原始参数，带原文身份信息
_legacy/                      来源不明的原件 + 溯源档案
_internal/                    项目内部记忆（含原文标题与链接）
```

纯标准库，零依赖，`python3` 直接跑。

---

## 关于「外部同类排版技能」

同类开源技能（如 TierFlow-Design）的做法是：内置一套固定组件库，装配生成。这套结构值得抄的是「组件库 + 校验 + 0 ERROR 门槛」这一层，组件本身得自己写。

这里没复制任何一个外部组件。定位区别：

- 外部技能 → 内置固定模板，谁用都一样
- 这里 → 从参考文章学排版，做可读性转换，再变你自己的主题

固定模板谁都能拿走，学来的风格不是。

---

## 来源说明（公开树的构成，2026-10-04）

**随仓库发布的内容全部为本项目原创**：`README.md`、`gzh.py`、`gzh_extract.py`、`style_to_theme.py`、
`wechat_render.py`、`validate_gzh_html.py`、`desensitize.py`、`components/`、
`themes-public/`、`my-styles-public/`、`example-article*`。没有任何一行来自外部项目。

**项目早期有一批提取脚本**（`wechat_style_extractor.py`、`server.py`、`compare_styles.py`、
`batch_polish.py`、`wechat_polisher.py` 及若干 shell 脚本），来自网络，但**当时目录里没有它们的
LICENSE 与出处声明**。查过一轮：用四组代码特征（`wechat_style_extractor`/`is_accent_color`/
`pixel_value`/`build_result`）做公开代码搜索没有命中同源仓库；看着像的两个都不是同一份
（`sennkuwu/wechat-style-extractor` 是 Next.js + TypeScript 版，
`IT-Althusser/wechat-writer-skills` 的 `learn_theme.py` 是 BeautifulSoup + YAML 版）。

没标注许可证的代码，法律上默认「保留所有权利」，没法拿去开源。处理方式是：

- 提取层重新自写了一遍（`gzh_extract.py`，纯标准库），**输出字段与旧版同构**，
  已有的 `my-styles/*.json` 一行都不用改就能接着用；
- 原件连同全部 21 个原始文件封存在 `_legacy/`，**不进公开树**，溯源线索写在 `_legacy/README.md`；
- git 历史清干净了（旧的那次 init commit 里满是原件，换了个干净 root commit）。

如果你也在整理类似的脚本，这是条可走的路：来源不明的片段别硬留，重写一遍成本比补 license 低。

### 仓库里为什么有两套主题目录

| 目录 | 内容 | 去向 |
|---|---|---|
| `themes/`、`my-styles/` | 从参考文章提取的原始参数，带原文标题 / 公众号名 / 文章链接 | 本地保留，**不进仓库** |
| `themes-public/`、`my-styles-public/` | 同一批参数去掉身份信息后的版本，色值与排版参数不变 | **进仓库**，随代码发布 |

`desensitize.py` 做的就是这件事：`python3 gzh.py public` 重新生成并顺手体检一遍。
只有登记在 `PUBLIC_NAMES` 里的主题才会被拷进公开目录 —— 新加的主题想公开，往那张表里加一行
（`自己的名字: 自己的名字`）再跑一次就行。顺带让「内部存档被 `gzh.py public` 顺手推上去」变成不可能：
没登记的会被 `[skip]` 掉，`--check` 还会把已经混进公开目录的文件名报出来。

注意 `themes/` 和 `themes-public/` 渲染器两个都认（搜索顺序：内部优先）。这不是为了隐藏什么，
是因为 `themes/` 不进仓库 —— 只认它的话，clone 下来的人 `--theme` 任何主题都会报「找不到主题」。

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
- 有些文章的颜色写在非元素 style 上（外层 section 或内联 class），提取器抓不到时主题会回落到自带版式配色，不影响出稿。
- 提取层只接受 `mp.weixin.qq.com` 的 https 链接，返回验证页时会明确报错（说明被限流了，换篇或等会儿）。
- 主题名带 `.json` 后缀也能传，不带会自动补。名字里有空格的话需要引号包一下。
