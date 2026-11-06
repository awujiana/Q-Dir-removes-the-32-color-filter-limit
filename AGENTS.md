# AGENTS.md

> 本文件供 **AI 编码 / 写作 agent**（如 WorkBuddy）阅读，用于了解本仓库的结构、约定与禁忌，从而在自动改动时保持风格一致。
> 人类贡献者请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)（含完整命名规范）。

## 项目概述

- **名称**：Q-Dir 颜色过滤器扩容补丁（中文名）
- **GitHub 仓库名（英文名）**：Q-Dir-removes-the-32-color-filter-limit
- **类型**：代码仓库（Python 工具 + 文档，MIT）
- **维护者**：awujiana
- **一句话**：用 PE 二进制补丁把 Q-Dir 12.77 x64 的颜色过滤器上限从 32 条提升到最多 127 条，自动定位、可回滚、写盘后复检。

## 仓库结构

| 路径 | 用途 | 是否发布 |
| --- | --- | --- |
| `qdir_colorfilter_unlimit.py` | 主脚本：目标定位、PE 校验、追加 `.qdcol` 节、迁移数组、改上限、重定位引用、静态复检、备份还原 | ✅ |
| `qdir_colorfilter_unlimit.md` | 开发文档：地址模型、全局常量、核心流程、复检 | ✅ |
| `Q-Dir颜色过滤器扩容_使用指南.md` | 使用指南：三分钟速查、环境准备、自动定位、常见问题 | ✅ |
| `deploy_v8_report.md` | 一次 v8 应用记录（结构变化、运行时验证、回滚方式） | ✅（历史记录） |
| `README.md` | 对外说明（awujiana 风格） | ✅ |
| `CONTRIBUTING.md` | 贡献指南（含命名规范） | ✅ |
| `AGENTS.md` | 本文件（给 AI 看的内容） | ✅ |
| `CHANGELOG.md` | 更新日志 | ✅ |
| `LICENSE` | MIT 协议全文 | ✅ |
| `.gitignore` | 排除 Python 缓存、补丁产物与备份 | ✅ |

## 必须遵守的约定

1. **命名规范（不缩写）**：Python 模块 / 函数 / 变量 `snake_case`、类 `PascalCase`、常量 `UPPER_SNAKE_CASE`，一律全拼无缩写、名称不重复。详见 `CONTRIBUTING.md` 的「命名规范（不缩写）」。
2. **项目核心不变量（改坏即失效）**：
   - **版本锁定**：只对 **Q-Dir 12.77 x64** 生效。关键地址：`ARRAY_RVA=0x1544F0`、`ARRAY_STRIDE=0x20`、`COUNT_RVA=0x15447C`、`ImageBase=0x400000`；`LOOP_SITES` 五处上限点、`RENDER_GUARD=0x4B3A6C`、`INIT_CLEAR=0x522C8B`、`EXPECTED_REF_VAS` 共 17 处引用。特征不匹配必须**拒绝执行**，不得放宽校验去「强行打补丁」。
   - **不得覆盖哨兵**：颜色数组迁移到新节 `.qdcol` 时，**不得覆盖 `0x1548F0` 处的对象管理结构**——它是 Q-Dir 的对象管理哨兵，不是颜色数组的一部分（历史踩坑）。
   - **上限 ≤ 127**：代码用 `cmp r32, imm8` 有符号立即数，超过 127 无法编码。
   - **默认不改原文件**：默认生成补丁副本；只有 `--in-place` 才替换，且必须保留 `.bak` / `.orig` 备份，`--restore` 可还原。
   - **写盘后必须复检**：`Target.verify()` 需核对节表、引用重定位与上限常量，失败即报错。
3. **技术禁令**：
   - 不得把本工具用于其它版本的 Q-Dir（地址与特征全变，必崩）。
   - 不得把 `--max` 设到 127 以上。
   - 不得删除或绕过 `.orig` / `.bak` 备份与 `--restore` 逻辑。
   - 不得在未校验 PE 特征（AMD64、节表、目标地址）时写盘。
4. **README 风格**：顶部 shields.io 徽章（`<p align="center">` 纯 HTML 居中）→ 双名标题 → 语言切换徽章 + 文档导航 → `[!WARNING]` AI 声明 → 目录 → 正文 → 关联标签 → 底部三节（关联仓库 / 作者联系方式 / 开源协议）。
5. **双名标题**：README 顶部**中文名 `<h1>` 在上、GitHub 仓库名 / 英文名 `<h2>` 在下**，两者都要有。
6. **协议**：**MIT**（沿用仓库既有 `LICENSE`；技能默认代码仓库为 AGPL-3.0，如需切换须显式决定并替换 `LICENSE` 全文）。
7. **文档索引**：「文档」节只列**操作 / 参考文档**；部署报告 `deploy_v8_report.md` 作为历史记录，不单独成节。
8. **提交信息**：说明「做了什么 / 为什么」；从 `main` 切特性分支（单人仓库可直接提交）。
9. **提交身份**：`git config user.name` 必须是 `awujiana`，`user.email` 必须是 `bingshanlengtie@qq.com`。旧邮箱一旦进了提交元数据，「改文件」和 `force push` 都清不掉。
10. **维护**：每次改动同步 `CHANGELOG.md`（Keep a Changelog，语义化版本）。
11. **徽章必须居中**：用 `<p align="center">` 包纯 HTML `<a><img></a>`，不要用 Markdown 图片语法；语言徽章三态为当前绿 / 可切换蓝 / 待补灰（无链接）。
12. **锚点稳定**：README 标题用显式 `<a id="sec-N"></a>` + TOC `#sec-N`，保证长文档链接不失效。
13. **关联标签**：README 增设「🏷 关联标签」节（居中 shields.io 徽章），并同步设置 GitHub Topics（`gh repo edit <owner>/<repo> --add-topic "..."`）。

## 改动前检查

- **改 `qdir_colorfilter_unlimit.py`**：`python -m py_compile qdir_colorfilter_unlimit.py` 检查语法；改动地址 / 上限 / 引用表后，必须在 Q-Dir 12.77 x64 上跑 `python qdir_colorfilter_unlimit.py --check` 与一次完整打补丁 + 复检。
- **定位相关改动**：`python qdir_colorfilter_unlimit.py --list` 确认候选与打分符合预期。
- **改文档**：正文与脚本行为不一致时以脚本为准，并同步 `qdir_colorfilter_unlimit.md`、`Q-Dir颜色过滤器扩容_使用指南.md` 与 `CHANGELOG.md`。
- **提交**：`git status` 确认不含 `__pycache__/`、`*.pyc`、`Q-Dir_patched*.exe`、`*.bak*`、`*.orig`。

## 不要做的事

- 不要手写 `⚠️ Warning` 代替 `> [!WARNING]`。
- 不要缩写命名、不要同名文件（含仅大小写不同）、不要用数字后缀解决冲突（`handle2` ❌）。
- 不要在标题用 VS16 变体 emoji（`⚠️` / `🖼️`）。
- 不要改动 `ARRAY_RVA` / `COUNT_RVA` / `LOOP_SITES` / `RENDER_GUARD` / `INIT_CLEAR` / `EXPECTED_REF_VAS` 而不同步文档与复检。
- 不要覆盖 `0x1548F0` 处的对象管理结构。
- 不要把补丁产物与备份（`Q-Dir_patched*.exe`、`*.bak*`、`*.orig`）提交进仓库。
- 不要删除 `AGENTS.md` / `CONTRIBUTING.md` / `CHANGELOG.md`；它们承载协作与 AI 约定。
