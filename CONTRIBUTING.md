<div align="center">

<p align="center">
  <a href="LICENSE"><img alt="协议 MIT" src="https://img.shields.io/badge/协议-MIT-green?style=flat"></a>
  <a href="CONTRIBUTING.md"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat"></a>
  <a href="https://github.com/awujiana"><img alt="AI辅助生成 是" src="https://img.shields.io/badge/AI辅助生成-是-orange?style=flat"></a>
</p>

<h1>贡献指南</h1>

<strong>欢迎参与「Q-Dir 颜色过滤器扩容补丁」的共建</strong>

</div>

---

> [!WARNING]
> 本项目的相当一部分代码由 AI 辅助生成，并经过持续的人工作业、联调和重构，但它仍然可能存在遗漏、边界情况处理不足或行为与预期不完全一致的问题。如果你在使用过程中发现 Bug、兼容性问题、异常行为或文档缺失，欢迎积极提交 Issue。最好附上复现步骤、日志、截图和系统版本信息，这会非常有帮助。

感谢你关注 **Q-Dir 颜色过滤器扩容补丁** 并愿意贡献。本协议与流程用于确保协作顺畅、输出风格统一、许可证一致。

> 维护者：awujiana ｜ 开源协议：以仓库 `LICENSE` 为准（MIT）

## 📚 目录

- [我能如何参与](#我能如何参与)
- [提交 Issue 前](#提交-issue-前)
- [提交 Pull Request 前](#提交-pull-request-前)
- [命名规范（不缩写）](#命名规范不缩写)
- [代码与文档约定](#代码与文档约定)
- [行为准则](#行为准则)
- [许可证](#许可证)

## 🤝 我能如何参与

- **提交 Issue**：反馈补丁失败、目标定位异常、文档错误或新场景需求（附 Q-Dir 版本号）。
- **完善文档**：改进使用指南与开发文档，补充常见问题。
- **改进脚本**：优化目标定位打分、错误提示、复检逻辑（须保持对 12.77 x64 的特征校验）。
- **补充测试样本**：提供不同安装方式下的目录结构（无需上传 EXE 本体）。

## 🐞 提交 Issue 前

1. 先搜索确认问题未被重复提出。
2. 说明环境：Windows 版本、Q-Dir 版本号（如 `12.77 x64`）、Python 版本、`pefile` / `capstone` 版本。
3. 附上完整命令行输出（可用 `--check` / `--list` 的输出来说明目标定位情况）。
4. 说明是「定位失败」「特征不匹配」「写入失败」还是「补丁后异常」，便于分类。

## 🔀 提交 Pull Request 前

1. 从 `main` 分支切出特性分支，命名如 `fix/candidate-scoring` 或 `docs/usage-guide`。
2. 遵循本仓库的 README 输出规范：
   - 顶部使用 shields.io 徽章表示协议 / 平台 / 作者等元信息，徽章必须用 `<p align="center">` + 纯 HTML 居中；
   - 正文含项目简介、核心特色、快速开始、注意事项；
   - 代码仓库顶部须有 AI 辅助生成声明的 `> [!WARNING]` 警示块；
   - 命名一律全拼、禁止缩写、名称不重复（见下文「命名规范（不缩写）」）；
   - 底部必须包含「关联仓库」「作者联系方式」「开源协议」。
3. 涉及地址常量、上限点、引用表的改动，必须同步更新 `qdir_colorfilter_unlimit.md`，并在 PR 描述里说明验证方式。
4. 提交信息清晰说明「做了什么 / 为什么」。

## 📝 命名规范（不缩写）

> 本节为**硬性命名规范**，所有改动都必须遵守。完整对照表与反例见技能 `awujiana-readme-style` 的 `references/naming-conventions.md`。

### 总则

- **一律全拼，禁止缩写**：`usr`→`user`、`cfg`→`config`、`btn`→`button`、`img`→`image`、`msg`→`message`、`err`→`error`、`idx`→`index`。
- **名称不重复**：项目名全局唯一；同目录文件名唯一（大小写不敏感）；同模块符号唯一。
- **名称即语义**：只看名字即可判断用途；禁止 `utils`、`common`、`misc`、`temp`、`data1`、`file2` 等泛化名。

### 项目（仓库）命名

- 规范要求 `kebab-case`、全小写、2–5 个单词。本仓库现名 `Q-Dir-removes-the-32-color-filter-limit` 为历史命名，**不强制重命名**，但新项目应遵守规范。
- 禁止含版本号、日期、作者名，以及 `test` / `demo` / `new-project` / `untitled` 等无信息量名称。

### 文件命名（Python 项目）

| 类型 | 规则 | 示例 |
| --- | --- | --- |
| Python 模块 | `snake_case.py` | `qdir_colorfilter_unlimit.py` |
| 文档 | `kebab-case.md` | `usage-guide.md` |
| 常量 | `UPPER_SNAKE_CASE` 导出 | `ARRAY_RVA`、`COUNT_RVA` |
| 测试 | `test_<模块>.py` | `test_qdir_colorfilter_unlimit.py` |

- **同一目录内不得出现同名文件**，包括仅大小写不同。
- 避免用 `util.py`、`common.py` 这类无信息量的模块名。

### 函数与类命名（Python 遵循 PEP 8）

- **函数 / 变量**：`snake_case`，**动词开头 + 名词**，全拼，如 `find_candidates`、`resolve_exe`、`apply_patch`。
- **类**：`PascalCase`，**名词**，全拼，如 `Target`、`Steps`。
- **内部辅助**：单下划线前缀，如 `_init_stdout`、`_want_color`。
- 同一模块内不得出现同名函数；不同模块同名须加限定词。
- 名称必须与用途一致：`score_candidate` 只做打分、`apply_patch` 只做打补丁，不混职责。

### 冲突处理

加**语义限定词**，而不是数字后缀。`handle2` ❌；应为 `handle_load` 与 `handle_save` ✅。

## 📋 代码与文档约定

- 正文以简体中文为主，专有名词（PE / RVA / RIP / Capstone）保留英文原文。
- 命令行、代码片段使用围栏代码块并标注语言。
- 对比 / 参数类信息优先使用表格。
- 标题层级连续，不跳级。
- **地址与常量是硬约束**：`ARRAY_RVA`、`COUNT_RVA`、`LOOP_SITES`、`RENDER_GUARD`、`INIT_CLEAR`、`EXPECTED_REF_VAS` 等必须与目标版本严格对应；改其一必须同步文档与复检逻辑。
- **徽章居中**：顶部徽章用 `<p align="center">` 包纯 HTML `<a><img></a>`，不要用 Markdown 图片语法。
- **不提交产物**：补丁产物（`Q-Dir_patched*.exe`）与备份（`*.bak*`、`*.orig`）不得入库，`.gitignore` 已排除。

## 🤗 行为准则

请保持友善、专业、就事论事。尊重不同经验水平的贡献者，对规范分歧以讨论达成共识，不人身攻击、不贬低他人工作。

## 📄 许可证

向本仓库提交贡献，即表示你同意以仓库 `LICENSE` 所载协议（MIT）发布你的贡献，并确认你拥有相应的授权。详见仓库内 [LICENSE](LICENSE)。

[![MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
