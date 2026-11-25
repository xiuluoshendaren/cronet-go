# Cronet 159 与旧版扩展参数 parity

## 目标与约束

核对旧 `1.patch`、旧原生库、恢复的旧 C ABI 及 `akamai-srv-api/src/cronet/engine_params.go` 使用的全部扩展参数。新版可支持的参数接入 IDL、C ABI、Go 绑定与 Chromium 配置解析；不可支持项记录明确原因。全程自主执行，不询问用户。

- 先验证 macOS arm64 dylib，通过后再构建 Linux x64/arm64。
- 单元测试通过 GoLand MCP 集成终端执行。
- 所有文件留在项目内；需要代理时仅使用 `127.0.0.1:8897`，Docker 使用 `host.docker.internal:8897`。
- 保留已有未提交改动；完成后 `git add .`、审查暂存内容并本地 Conventional Commits 提交，不推送。

## 工作包

| 编号 | 内容 | 状态 |
| --- | --- | --- |
| WP1 | 盘点旧补丁、旧库、下游全部扩展参数及 159 对应实现 | 已完成 |
| WP2 | 实现缺失配置入口、Go 绑定与针对性测试 | 已完成 |
| WP3 | 构建并验证 macOS arm64 dylib | 已完成 |
| WP4 | 构建并验证 Linux x64/arm64 so | 已完成 |
| WP5 | 更新迁移文档、记忆、产物清单并本地提交 | 已完成 |

## 执行记录

- 已确认新版尚未接入 `tls_cipher_suites`、`tls_curves`，旧 mapper 未迁移。
- `1.patch` 只含代理、认证、HTTP/2、构建和泄漏检查修改；TLS mapper 仅存在旧二进制。
- 旧库无 `enable_cookie_store` 字符串，且旧版、159 均显式禁用原生 CookieStore；不新增伪兼容入口。
- `X25519KYBER768` 两个别名在 159 已删除，无法恢复；其余旧 cipher/curve 名称接入。

- macOS arm64 构建成功；mapper 与 ordered cipher 符号存在；GoLand MCP 全量 `-race` 测试通过，实际 ClientHello 顺序验证通过。
- Linux x64 构建成功；`dist/linux-x64/libcronet.so` 为 ELF64 x86-64，mapper 与 ordered cipher 符号存在，SHA256 为 `8c539b88ab19ab269cbe6fe6d044cdd5910ab748abe30f760af45b2134cda719`。
- 修复历史半成品源码树重复插入四个桌面字段的问题；补丁会清理旧块后幂等续建。
- Linux x64 经 GoLand MCP 运行全量 `-race` 测试通过，包括实际 ClientHello TLS 参数测试；日志 `.build/logs/go-test-linux-x64.log`。
- Linux arm64 构建成功；`dist/linux-arm64/libcronet.so` 为 ELF64 AArch64，mapper 与 ordered cipher 符号存在，SHA256 为 `8ee445af2e216a5fade768b3e408840359d1e1636c62027058ae2de4066af41f`。
- Linux arm64 经 GoLand MCP 运行全量 `-race` 测试通过；日志 `.build/logs/go-test-linux-arm64.log`。三平台迁移与验证完成。
