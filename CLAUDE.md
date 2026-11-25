# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

cronet-go 将 Chromium Cronet 网络栈编译为 Go 可调用的 `.so` / `.dylib`，通过 CGO 提供原生绑定、HTTP 客户端与双向流适配。本仓库保存 Go 代码、Chromium 补丁及可复现构建脚本；Chromium 源码、工具和缓存位于项目内 `.build/`，新产物位于 `dist/`。

## Workflow Rules

1. **编码前先写计划** — 任何编码任务开始前，在 `.claude/plan/yyyy-MM-dd/` 创建带 `NN-` 编号的计划文件。计划让后续会话可追溯任务背景、决策与验证。
2. **大任务维护工作包清单** — 多步骤、多文件或多阶段任务，在计划中先列工作包表格：`编号 / 内容 / 状态`。状态只用 `待执行`、`执行中`、`已完成` 或 `阻塞（注明原因）`；开始某包立即回写“执行中”，完成立即回写“已完成”，不得在最后批量补写。计划与状态记录随任务提交。
3. **新会话先装载项目上下文** — 完整读取根目录 `CLAUDE.md` 和 `MEMORY.md`；遵循 `CLAUDE.md` 引用的项目规范。项目有 `.claude/skills/` 时，对当前任务适用的技能须先加载再执行。
4. **记忆索引保持完整** — 新增、重命名或删除 `.claude/memory/` 下记忆文件时，同步更新根目录 `MEMORY.md`；结束前确认索引链接与实际记忆一一对应。
5. **Agent 改动的文件必须本地提交** — 所有由 agent 操作（增、删、改）且应纳入版本控制的文件，都必须依次执行 `git add .`、`git commit`。commit message 用 Conventional Commits、准确描述改动。用户已说明不必远程推送，默认不执行 `git push`；只有用户明确要求远程交付时才推送，包括项目技能生成的报告。测试失败、冲突、权限拒绝或明确要求的推送失败时停止并如实报告。
6. **worktrees 与编号统一管理** — 所有 worktrees 放在 `.claude/worktrees/`；`.claude` 下生成文件按本 skill 的 `NN-` 编号规则命名。
7. **跨 agent 资源入口保持统一** — 项目根目录的 `.agents` 必须是指向 `.claude` 的相对符号链接，其他 agent 与 Claude 共用同一份 skills、memory 等资源，不复制维护第二份。

## 会话约定

- 使用中文回复；每次会话第一条回复前先加载 ultracave skill。宿主没有专用 Skill 工具时，读取可用技能目录中对应 SKILL.md；不可声称调用了不存在的工具。
- 保留用户要求的 `git add .`，提交前检查暂存范围与敏感内容。
- 根目录存在 `.codegraph/` 时，理解或定位代码前优先使用 MCP `codegraph_explore` 或 `codegraph explore "问题或符号"`；不存在时跳过，不自行建立索引。
- 所有生成文件存当前项目内；临时文件放 `.claude/tmp/`，不得复制示例中的代理凭证到文档、日志或新代码。

## Tech Stack

- 模块：`github.com/wmm1996528/cronet-go`；`go.mod` 声明 Go 1.21。
- 核心：Go、CGO、Cronet C API、Chromium C++ 网络栈；原生库在 Chromium 工作区通过 GN/Ninja 构建。
- HTTP 入口：标准库 `net/http`；本项目无独立 Web 服务或前端部署配置。
- 已有本地 HTTP/TLS/代理单测和 Docker 双架构构建；单元测试必须通过 GoLand MCP 执行。无数据库 migration。

## Architecture

`EngineParams` 配置 `Engine`，通过 Cronet C API 初始化网络上下文。`URLRequest` 配合 Executor、Callback 和 Buffer 处理异步请求，`transport.go` 将其适配为 `http.RoundTripper`。双向流走 `StreamEngine` / `BidirectionalStream`，`bidirectional_conn.go` 适配 `net.Conn`。

复用已有原生对象封装和回调注册机制；处理 C/Go 内存与回调生命周期时，先核对对应 Create/Destroy、锁、取消及完成路径。C API 的源定义位于 Chromium `components/cronet/native/cronet.idl`，头文件与实现应和 IDL 保持一致，不仅修改生成文件。

## Build & Run

先准备与目标系统、CPU 架构及定制 C API 匹配的 Cronet 头文件和动态库；Go 包没有内置 `#cgo` 路径配置。

```sh
export CGO_ENABLED=1
export CGO_CFLAGS="-I/usr/local/include/cronet"
export CGO_LDFLAGS="-Wl,-rpath,/usr/local/lib/cronet -L/usr/local/lib/cronet -lcronet"
go build .
go vet .
go test .
```

这些是完成原生依赖安装后的验证命令；自动化测试使用 `scripts/test_cronet.sh <目标>`，通过 GoLand MCP 集成终端运行。上述 `-lcronet` 要求库目录有对应平台的 `libcronet.so` 或 `libcronet.dylib`。Linux 附带版本化库名，使用前需正确安装或建立链接；不得把 macOS 的库用于 Linux，或混用 CPU 架构。

示例构建：`go build -o .claude/tmp/01-example1 ./examples/1`。只构建不运行；示例包含固定代理和外部目标。`examples/build.sh` 硬编码作者本地路径，不能原样复用。`examples/2/main.go` 只有 package 声明；`examples/3` 含不在当前 go.mod 中声明的旧模块引用，不能据此宣称所有示例可构建。

原生构建使用 `scripts/build_cronet.py` 和 `scripts/build_linux.sh`，细节见 `native/README.md`。版本固定在 `native/cronet.lock.json`；原始 `1.patch` 保留，当前迁移由 `scripts/prepare_cronet.py` 实现。159 网络栈配合 144 C ABI / grpc 兼容层，不能混淆两者版本。

## Key Files

- `1.patch`：代理规则、CONNECT 认证、HTTP/2 SETTINGS、请求泄漏检查和 Linux 构建适配补丁。
- `engine.go` / `engine_params.go`：引擎生命周期和配置；`SetProxyServer` 校验并拆分 URL 账号密码，返回 error；扩展见 `engine_proxy.go`、`engine_http2.go`。
- `url_request*.go` / `executor*.go` / `buffer*.go`：请求封装、回调及内存管理。
- `transport.go`：HTTP RoundTripper、响应体、上传与取消适配。
- `bidirectional_stream*.go` / `bidirectional_conn.go`：双向流接口与 net.Conn 适配。
- `examples/cronet/include/`：定制 C 头文件；`examples/cronet/VERSION` 标记 126.0.6462.0。
- `examples/cronet/libcronet.126.0.6462.0.so`：Linux x86-64；`examples/libcronet.dylib`：macOS arm64。

## 补丁迁移与验证

- 旧 `1.patch` 内的 CONNECT User-Agent 认证改写、反置随机区间、缺失 SETTINGS 枚举和放宽泄漏 CHECK 均不直接复用。
- 新版使用独立代理认证、HTTP/2 SETTINGS/GREASE 和显式证书忽略参数，IDL 与生成的 C ABI 一致。
- macOS arm64、Linux x64、Linux arm64 的 159 动态库均已编译，并通过 GoLand MCP 全量 `-race` 单测；TLS cipher/curve 入口和实际 ClientHello 顺序已验证。
- 维护 Buffer 所有权：成功 Read 转交 Cronet；OnReadCompleted 交还 Go；EOF/取消/错误由 Cronet 释放原生读取缓冲区。不得在终止回调中再次释放。
- 历史 examples 中的库与版本保持原样，新产物只写 dist，不能通过提交标题推断二进制版本。

## 发布

涉及上线、release、deploy、版本 tag 时，先加载 `.claude/skills/release-report/SKILL.md`。项目产物为 Go 模块及配套原生库，不是已确认的独立部署服务。原生产物重建方式、目标矩阵、分发渠道及下游重启顺序均需补证。
