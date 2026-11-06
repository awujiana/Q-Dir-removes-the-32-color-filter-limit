# 更新日志

本文件记录 `Q-Dir 颜色过滤器扩容补丁`（Q-Dir-removes-the-32-color-filter-limit）的重要变更，版本号遵循语义化版本 `MAJOR.MINOR.PATCH`。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [未发布]

### 新增

- 新增 awujiana 风格 `README.md`、`CONTRIBUTING.md`、`AGENTS.md`、`CHANGELOG.md` 与 `.gitignore`。

### 改进

- README 补充项目简介、核心特色、效果对比、快速开始、命令行参数、注意事项、文档索引、关联标签与底部三节。
- 约定中明确「仓库为单一真相、提交身份、补丁产物不入库」等规则。
- 开源协议由 **MIT** 改为 **AGPL-3.0**：`LICENSE` 替换为 AGPL-3.0 全文，README / CONTRIBUTING / AGENTS 同步更新。

## [1.0.0] - 2026-11-06

### 新增

- 首个有文档记录的版本：`qdir_colorfilter_unlimit.py` 将 Q-Dir 12.77 x64 颜色过滤器上限由 32 提升到最多 127。
- 使用指南 `Q-Dir颜色过滤器扩容_使用指南.md` 与开发文档 `qdir_colorfilter_unlimit.md`。
- v8 应用记录 `deploy_v8_report.md`（结构变化、运行时验证、回滚方式）。

### 已知限制

- 仅 Q-Dir 12.77 x64；其它版本因特征不匹配拒绝执行。
- 仅支持 64 位（AMD64）。
- 上限最大 127（`cmp r32, imm8` 有符号立即数）。

## 更早的版本

本仓库在 `2026-11-06` 之前已有脚本与 v8 应用记录，但未建立 `CHANGELOG.md`，此处不做追溯编造。
