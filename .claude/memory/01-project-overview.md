---
name: project-overview
description: cronet-go 的原生库构建、Go 适配、代理补丁与验证边界
metadata:
  type: project
---

# cronet-go

**当前状态**：已有 Go 绑定、Chromium 补丁和预编译库；已静态阅读，尚未验证原生重编译或网络请求。

**核心约束**：
- 用户目标：提取 Chromium Cronet，编译 Go 可调用的 so / dylib；重点关注 `1.patch`。
- 中文回复；会话先加载 ultracave；改动执行 git add、commit、push。规则与构建命令以根目录 CLAUDE.md 为准。
- Go 模块为 `github.com/wmm1996528/cronet-go`，go.mod 声明 Go 1.21；必须准备定制 C API、匹配架构的原生库与 CGO 编译链接参数。
- 附带 Linux x86-64 so（VERSION 为 126.0.6462.0）及 macOS arm64 dylib；未核实 dylib 的 Cronet 版本。提交标题 Chrome 144 不能替代产物版本证据。
- `1.patch` 含自定义代理规则；CONNECT 认证复用 user_agent；用户名/密码传递未见实际认证消费，Go 解析逻辑已注释。
- 补丁内随机分布上下界反置、SETTINGS_UNDEFINED_SIZE 定义缺失、IDL/生成结构不一致及 builder 重复 diff 均待目标 Chromium 源码验证。
- 无测试文件、CI、Dockerfile、SQL migration；不运行含固定代理与外部目标的示例。不得将示例凭证复制到新文件。
- 复用 Engine、URLRequest、Executor、Buffer 和双向流适配，注意原生对象生命周期及回调锁。
