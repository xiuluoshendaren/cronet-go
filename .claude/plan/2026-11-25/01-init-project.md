# 初始化项目计划

## 任务
为 cronet-go 创建 Claude Code 与其他 agent 共用的项目配置，保留现有代码和规则。

## 工作包

| 编号 | 内容 | 状态 |
| --- | --- | --- |
| WP1 | 分析项目代码库，识别技术栈、构建与测试命令 | 已完成 |
| WP2 | 创建目录、`.agents` 符号链接与 `.gitignore` 规则 | 已完成 |
| WP3 | 编写项目规则、记忆索引和项目概况 | 已完成 |
| WP4 | 创建项目级 release-report skill | 已完成 |
| WP5 | 验证配置、暂存、提交并推送 | 执行中 |

## 执行记录

- 2026-11-25：已有 `.gitignore` 仅忽略 `/.idea`；其余固定名配置及 `.agents` 均不存在。工作区干净，当前分支 main。
- 已读 README、go.mod、Go 原生绑定与适配层、示例脚本及完整 1.patch；本轮初始化不修改功能代码或二进制。
- 未发现测试文件、CI、Dockerfile、数据库 migration 或部署编排；示例构建脚本含作者机器绝对路径，不直接执行。
- 已创建相对链接 `.agents -> .claude`；保留 `/.idea`，追加本地设置、worktrees、临时文件忽略规则；未创建本地设置。
- 已写入统一规则入口、完整通用工作流、Go/CGO 构建前提、原生库架构和补丁验证边界；未记录示例凭证。
- 已生成 release-report：沿用本地 vMAJOR.MINOR.PATCH tag 风格（本地最大 v1.11.0），按 Go 模块与原生库分别判断发布范围；无 SQL。原生构建参数及分发渠道标记需确认。
- 首次 fetch 因 HTTP/2 framing error 失败，改用单次 HTTP/1.1 fetch 核实远端；未修改全局 Git 配置。
- HTTP/1.1 fetch 成功；配置文件、相对链接、记忆索引、编号与忽略规则验证通过，git diff --check 通过。仅配置文档改动，不运行原生编译或网络示例。
