# 公众号排版本地工具链变更记录

## 2026-10-04

### 修正内容
- **主题解析只认 `themes/`，导致 clone 下来 `--theme` 任何主题都报「找不到主题」**：
  `wechat_render.py` 的 `resolve_theme()` / `list_themes()` 原来只看 `themes/`，
  而该目录被 `.gitignore` 排除、不随仓库发布。修法是新增 `theme_dirs()`，按
  `themes/`（内部，优先）→ `themes-public/`（随仓库发布）顺序扫描。
  改前 clone 下来 `gzh.py list` 只剩默认版式、`gzh.py build --theme 参考一` 直接失败（实测复现）。
- `gzh.py list` 对脱敏主题打印空的「学自：」：现在显示为「脱敏公开版（无原文来源）」，
  因为 `themes-public/` 里的主题本来就没有原文身份字段。

### 新增内容
- `themes-public/` 与 `my-styles-public/` 随仓库发布，三个主题（`参考一`/`技术类`/`部署类`）
  clone 下来即可直接用，不需要自己提取。
- `TROUBLESHOOTING.md`：按现象索引的排查手册，8 节覆盖主题找不到、`--theme` 未生效、
  build 失败、限流、作者占位、提取回落、校验报错、WARN 竖条。
- `CHANGELOG.md`：本文件。
- README 按文档规范重写：补「最后验证」时间戳块、适用对象、不适合谁、五步快速开始
  （每步带可验证输出）、口径脚注、文档地图交叉链接。
- `validate_gzh_html.py` 的 R6 规则从「`<img>` 缺 style」明确为「`<img>` 必须带 `style`」，
  README 的校验规则表同步更新（补上 WARN 四条）。

### 删除内容
- README 里「已知限制」中与新手册重复的条目，统一收进 `TROUBLESHOOTING.md`，
  README 只留四条最常用限制。

## 2026-10-04（更早，合并进首个 root commit）

### 修正内容
- 主题名从带原文标题的长名改成中性短名（`参考一`/`技术类`/`部署类`），
  原先的名字包含内部分类黑话。
- `gzh.py cmd_render` 未把 `--theme` 透传给渲染器（静默走默认版式、退出码仍为 0）。
- 校验器对嵌套 `<span>` 用布尔量判断导致误报（改为深度计数）。
- 提取层 HTMLParser 偏移错误、强调色只在「文字最多一半」的片段里取众数导致 H2 强调色被挤掉。
- `gzh.py run()` 的 `print` 未 flush，管道重定向时标题排到结果后面。

### 新增内容
- 四段闭环（`extract` → `theme` → `render` → `validate`），纯标准库零依赖。
- `gzh.py` 统一入口：`list` / `extract` / `theme` / `render` / `validate` / `build` / `diff` / `public` / `pipeline`。
- `desensitize.py` 脱敏：确定性变换生成公开版 + `--check` 检漏（URL / 身份字段 / ≥8 连续中文）。
- 清掉公开树里的内部称谓与决策流水账。

### 删除内容
- 公开树里 21 个来源不明的原件（无 LICENSE、无出处声明），全部封存进 `_legacy/`，不进仓库。
- git 旧历史（唯一一次 `init` commit 装了全部原件）：换成干净 root commit，
  旧历史只留在本地备份目录。
