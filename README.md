<div align="center">

<!-- badges:start -->
<p align="center">
  <a href="LICENSE"><img alt="协议 AGPL-3.0" src="https://img.shields.io/badge/协议-AGPL--3.0-blue?style=flat"></a>
  <a href="https://github.com/awujiana/Q-Dir-removes-the-32-color-filter-limit"><img alt="平台 Windows" src="https://img.shields.io/badge/平台-Windows-blue?style=flat"></a>
  <a href="https://github.com/awujiana/Q-Dir-removes-the-32-color-filter-limit"><img alt="语言 Python" src="https://img.shields.io/badge/Python-3.7%2B-blue?style=flat&logo=python&logoColor=white"></a>
  <a href="https://github.com/awujiana"><img alt="作者 awujiana" src="https://img.shields.io/badge/作者-awujiana-orange?style=flat"></a>
  <a href="https://github.com/awujiana/Q-Dir-removes-the-32-color-filter-limit"><img alt="状态 维护中" src="https://img.shields.io/badge/状态-维护中-green?style=flat"></a>
  <a href="https://github.com/awujiana/Q-Dir-removes-the-32-color-filter-limit"><img alt="AI辅助生成 是" src="https://img.shields.io/badge/AI辅助生成-是-orange?style=flat"></a>
</p>
<!-- badges:end -->

<a id="top"></a>
<h1>Q-Dir 颜色过滤器扩容补丁</h1>
<h2>Q-Dir-removes-the-32-color-filter-limit</h2>

<strong>解除 Q-Dir 颜色过滤器（Color Filter）写死的 32 条上限，最多可扩到 127 条；基于 PE 二进制补丁，自动定位、可回滚、写盘后静态复检。</strong>

<!-- language-nav:start -->
<p align="center">
  <a href="README.md"><img alt="简体中文 当前" src="https://img.shields.io/badge/简体中文-当前-2ea44f?style=flat"></a>
  <img alt="繁體中文 待补" src="https://img.shields.io/badge/繁體中文-待补-lightgrey?style=flat">
  <img alt="English 待补" src="https://img.shields.io/badge/English-待补-lightgrey?style=flat">
</p>

<p align="center">
  <sub>文档 / Docs：<a href="#sec-7">文档索引</a> · <a href="CONTRIBUTING.md">贡献指南</a> · <a href="CHANGELOG.md">更新日志</a> · <a href="#sec-8">多语言支持</a></sub>
</p>
<!-- language-nav:end -->

</div>

---

> [!WARNING]
> 本项目的相当一部分代码由 AI 辅助生成，并经过持续的人工作业、联调与重构，但它仍然可能存在遗漏、边界情况处理不足或行为与预期不完全一致的问题。如果你在使用过程中发现 Bug、兼容性问题、异常行为或文档缺失，欢迎积极提交 Issue。最好附上复现步骤、日志、截图和系统版本信息，这会非常有帮助。

<a id="sec-1"></a>
## 📚 目录

- [项目简介](#sec-2)
- [核心特色](#sec-3)
- [快速开始](#sec-4)
- [命令行参数](#sec-5)
- [注意事项](#sec-6)
- [文档](#sec-7)
- [多语言支持](#sec-8)
- [反馈建议](#sec-9)
- [参考与致谢](#sec-10)
- [关联标签](#sec-11)
- [关联仓库](#sec-12)
- [作者联系方式](#sec-13)
- [开源协议](#sec-14)

<a id="sec-2"></a>
## 🚀 项目简介

`Q-Dir 颜色过滤器扩容补丁` 是一个面向 **Q-Dir 12.77 x64** 的 PE 二进制补丁工具，由 **awujiana** 维护。它解除 Q-Dir 颜色筛选器（Color Filter）写死的 **32 条规则上限**，最多可扩到 **127 条**。

Q-Dir 在代码里把颜色过滤器上限固定为 32 条：超过 32 条后，多出来的规则要么存不进去，要么在载入时被截断。本项目通过修改 PE 文件解除该限制：

- 在 PE 中追加新区段 `.qdcol`，把原本 `32 × 32` 字节的颜色规则数组**整体搬迁**过去（原位置后面紧跟 Q-Dir 的对象管理结构，直接扩展会踩坏它）；
- 把载入 / 保存 / 解析路径中散落的 **5 处上限常量** `0x20（32）` 改成新上限；
- 修正颜色渲染阶段的样式索引守卫（`0..31`）与启动时的清理循环上限；
- 将 **17 处**引用该数组的指令重定位到新地址；
- 写盘后**自动静态复检**，确认改动全部落位。

> 本项目只针对预先分析过的 Q-Dir 版本与固定地址特征工作，**不是**通用 PE 修改器，也不应直接用于其它版本的 Q-Dir。

<a id="sec-3"></a>
## ✨ 核心特色

- **自动定位**：无需手填路径，按脚本目录、工作目录、父目录及常见安装子目录（`Q-Dir` / `Q-Dir_Portable_x64` / `x64` / `x84` 等）搜索，按「命名 + 位数 + 目录层级」打分自动挑选，跳过备份 / 补丁产物。
- **可回滚**：默认不修改原文件，生成补丁副本；`--in-place` 才替换，并保留 `.bak` / `.orig` 备份，`--restore` 一键还原。
- **上限可调**：`--max` 指定新上限（默认 127，最大 127）。
- **特征校验**：确认目标为 AMD64 PE、地址特征与预期一致才动手，版本不匹配直接拒绝执行（这是保护，不是 Bug）。
- **写盘复检**：补丁写入后执行静态复检，核对节表、引用重定位与上限常量。
- **自带说明**：`--guide` 打印完整指引，`--list` 列出候选 exe，`--check` 只检查状态。

### 效果对比

| 项目 | 原版 | 补丁版 |
| --- | ---: | ---: |
| 颜色过滤器上限 | 32 | **127（可调）** |
| 载入 / 保存 / 解析上限常量 | 32 | 127 |
| 渲染守卫（样式索引上限） | 31 | 127 |
| 启动清理上限 | 31 | 126 |
| 新增 PE 节 | — | `.qdcol` |

<a id="sec-4"></a>
## 📦 快速开始

### 1. 环境准备

需要 **Windows**（Q-Dir 为 Windows 程序）与 **Python 3.7+**：

```bash
pip install pefile capstone
```

> `pefile` 读取 PE 头与节表，`capstone` 反汇编 `.text` 识别 RIP 相对引用。缺依赖时脚本会提示安装命令。

### 2. 关闭 Q-Dir

打补丁前**先退出正在运行的 Q-Dir**，否则可能遇到文件占用（`写入失败: ...文件被占用或只读`）。

### 3. 检查与打补丁

```bash
# 看看现在的 Q-Dir 能不能打补丁
python qdir_colorfilter_unlimit.py --check

# 直接打补丁（不动原文件，生成补丁副本）
python qdir_colorfilter_unlimit.py

# 打完补丁直接替换原文件
python qdir_colorfilter_unlimit.py --in-place

# 只想扩到 64 条
python qdir_colorfilter_unlimit.py --max 64

# 后悔了，还原
python qdir_colorfilter_unlimit.py --restore
```

> 完整、面向使用者的图文步骤见 [使用指南](Q-Dir颜色过滤器扩容_使用指南.md)。

<a id="sec-5"></a>
## 🧩 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--exe` | 目标文件名，默认 `Q-Dir.exe` |
| `--dir` | 把搜索范围限定在该目录内 |
| `--search-dir` | 追加搜索目录（可多次） |
| `--depth` | 搜索目录深度，默认 `3` |
| `--pick N` | 候选多个时选第 N 个 |
| `--include-backup` | 搜索时包含备份 / 补丁产物 |
| `--list` | 只列出候选 exe 并退出 |
| `--max N` | 新上限，默认 `127`，最大 `127` |
| `--out` | 输出文件路径 |
| `--in-place` | 直接替换目标文件 |
| `--no-reloc` | 不迁移颜色数组（不推荐） |
| `--only` | 只执行指定步骤 |
| `--force` | 跳过部分校验（谨慎使用） |
| `--check` | 只检查目标文件状态 |
| `--restore` | 用 `.orig` 备份还原目标文件 |
| `--quiet` | 只输出关键结果与错误 |
| `--guide` | 打印完整指引 |
| `--color` / `--no-color` | 强制开 / 关彩色输出 |

<a id="sec-6"></a>
## ⚠️ 注意事项

- **版本限定**：只在 **Q-Dir 12.77 x64** 验证；其它版本几乎一定因特征不匹配而拒绝执行。
- **仅 64 位**：只支持 AMD64，32 位版本不适用。
- **上限最大 127**：代码使用 `cmp r32, imm8` 有符号立即数，超过 127 无法编码。
- **先关 Q-Dir**：打补丁前退出程序，避免文件占用。
- **默认不动原文件**：默认生成补丁副本；确认无误后再 `--in-place`，并保留备份。
- **保留备份**：不要删除 `.orig` / `.bak`，它们是回滚的依据。

<a id="sec-7"></a>
## 📖 文档

> 本节仅索引**操作 / 参考文档**（面向使用者与开发者）。

- [Q-Dir 颜色过滤器扩容 · 使用指南](Q-Dir颜色过滤器扩容_使用指南.md) — 面向使用者：三分钟速查、环境准备、自动定位、常见问题。
- [qdir_colorfilter_unlimit.py 文档](qdir_colorfilter_unlimit.md) — 面向开发者：地址模型、全局常量、核心流程与复检。
- 部署应用记录见 `deploy_v8_report.md`（一次性应用报告，非操作文档，不单独成节）。

> 本项目无独立测试套件；改动后可用 `python -m py_compile qdir_colorfilter_unlimit.py` 与 `--check` 自测。

<a id="sec-8"></a>
## 🌐 多语言支持

当前提供**简体中文**版本；其他语言的可用状态以顶部语言徽章为准（绿色「当前」/ 蓝色「切換」/ 灰色「待补」）。

> 新增语言：复制 `README.md` 为 `README.<locale>.md` 并翻译，在顶部语言徽章区补充对应徽章（已有译文用蓝色「切換」并加链接，未提供用灰色「待补」且无死链）。

<a id="sec-9"></a>
## 💬 反馈建议

提交 Issue 时建议附上：

- Windows 版本与 Q-Dir 版本号
- Python 版本与 `pefile` / `capstone` 版本
- 复现步骤与完整命令行输出
- 报错截图或日志

<a id="sec-10"></a>
## 🙏 参考与致谢

- **Q-Dir**：由 Nenad Hrg（SoftwareOK）开发的 Windows 多窗格文件管理器。本项目为**非官方**补丁，与 Q-Dir 官方无关。
- [pefile](https://github.com/erocarrera/pefile)：PE 文件解析。
- [Capstone](https://www.capstone-engine.org/)：反汇编引擎，用于识别 RIP 相对引用。

<a id="sec-11"></a>
## 🏷 关联标签

<p align="center">
  <a href="https://github.com/topics/q-dir"><img alt="q-dir" src="https://img.shields.io/badge/q--dir-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/windows"><img alt="windows" src="https://img.shields.io/badge/windows-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/python"><img alt="python" src="https://img.shields.io/badge/python-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/pe-patch"><img alt="pe-patch" src="https://img.shields.io/badge/pe--patch-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/binary-patch"><img alt="binary-patch" src="https://img.shields.io/badge/binary--patch-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/color-filter"><img alt="color-filter" src="https://img.shields.io/badge/color--filter-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/reverse-engineering"><img alt="reverse-engineering" src="https://img.shields.io/badge/reverse--engineering-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/capstone"><img alt="capstone" src="https://img.shields.io/badge/capstone-1f6feb?style=flat-square"></a>
  <a href="https://github.com/topics/pefile"><img alt="pefile" src="https://img.shields.io/badge/pefile-1f6feb?style=flat-square"></a>
</p>

> 以上为本仓库的 GitHub Topics（关联标签）；可在仓库首页 Topics 区或 `gh repo edit awujiana/Q-Dir-removes-the-32-color-filter-limit --add-topic "..."` 维护。

<a id="sec-12"></a>
## 🔗 关联仓库

- [awujiana/Q-Dir-removes-the-32-color-filter-limit](https://github.com/awujiana/Q-Dir-removes-the-32-color-filter-limit) — 本仓库
- [awujiana/awujiana-readme-style](https://github.com/awujiana/awujiana-readme-style) — 本仓库 README 风格来源

<a id="sec-13"></a>
## 📮 作者联系方式

- **作者**：awujiana
- **GitHub**：[@awujiana](https://github.com/awujiana)
- **邮箱**：bingshanlengtie@qq.com

<a id="sec-14"></a>
## 📄 开源协议

本项目基于 **[AGPL-3.0](LICENSE)**（GNU Affero General Public License v3.0）开源。

根据 AGPL-3.0 的要求：任何人使用、修改或分发本项目代码，若以网络服务器形式向用户提供交互服务，必须同样以 AGPL-3.0 公开其完整对应源代码。

版权所有 © awujiana。
