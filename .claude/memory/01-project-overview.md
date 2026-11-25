---
name: project-overview
description: cronet-go 的原生库构建、Go 适配、代理补丁与验证边界
metadata:
  type: project
---

# cronet-go

**当前状态**：已实现 Chromium 159.0.8154.34 的可复现提取；macOS arm64、Linux x64、Linux arm64 动态库均已编译，并通过 GoLand MCP 全量 `-race` 测试。旧 TLS cipher/curve 配置入口已恢复，实际 ClientHello 顺序验证通过。

**核心约束**：
- 用户要求自主完成，所有文件在项目内，需要代理时仅使用 127.0.0.1:8897；Docker 用 host.docker.internal:8897。
- 中文回复；会话先加载 ultracave；改动执行 git add . 和本地 Conventional Commits；不远程推送。
- 单元测试通过 GoLand MCP 集成终端运行，不能以普通终端测试代替。示例含固定凭证，禁止运行或复制到新文件。
- Chromium 159 删除了 C ABI / grpc_support，仅恢复 144.0.7559.0 兼容层并适配 159 接口；网络栈和 Cronet common 使用 159。
- 锁定输入在 native/cronet.lock.json；源码、工具、缓存放 .build，打包产物放 dist，均不纳入 Git。
- 代理、HTTP/CONNECT 认证、显式 SSL 忽略、HTTP/2 自定义 SETTINGS / GREASE 已实现；默认正常校验证书，SOCKS 认证返回不支持。
- `tls_cipher_suites`、`tls_curves` 已接入 experimental JSON 与 Go 辅助方法；159 已删除的 draft Kyber 两个旧别名只能 WARNING 并忽略。原生 CookieStore 在旧版和 159 均禁用，不伪造 `enable_cookie_store` 入口。
- 原始 1.patch 保留；迁移对照和构建说明见 native/README.md；旧随机区间、User-Agent 认证改写及放宽泄漏 CHECK 不照搬。
- 读取 Buffer 成功后归 Cronet，只有 OnReadCompleted 交还 Go；EOF/失败/取消时由 Cronet 释放，不得二次释放。
- 已完成计划：`.claude/plan/2026-11-25/02-refresh-cronet.md`、`.claude/plan/2026-11-25/03-tls-parameter-parity.md`。
