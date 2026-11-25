# 最新 Chrome Cronet 提取与构建

## 目标与约束

确认当前官方 Chrome 稳定版并固定 Chromium revision，移植自定义代理、代理认证、显式忽略证书校验及必要的既有定制。先编译 macOS arm64 dylib 并通过 GoLand MCP 验证，再构建 Docker 多平台 Linux so。

- 所有源码、工具、缓存、日志与产物均放当前项目目录；需要代理时仅使用 127.0.0.1:8897。
- 自主执行，不询问用户；默认仅本地提交，不推送。
- 旧 1.patch 保留作迁移依据，不直接套用已知有问题的随机 SETTINGS 或 User-Agent 认证改写。
- TLS 校验默认启用，仅通过明确的引擎参数关闭。

## 工作包

| 编号 | 内容 | 状态 |
| --- | --- | --- |
| WP1 | 核实官方版本、源码 API、宿主工具与 GoLand MCP | 已完成 |
| WP2 | 获取项目内源码和构建工具，编写可复现构建与补丁 | 已完成 |
| WP3 | Go 绑定与代理、TLS、生命周期适配 | 已完成 |
| WP4 | 编译 macOS dylib，通过 GoLand MCP 运行测试 | 已完成 |
| WP5 | Docker 多平台 Linux so 构建与验证 | 已完成 |
| WP6 | 文档、产物清单、记忆和本地提交 | 已完成 |

## 执行记录

- 宿主 macOS arm64，32 GiB 内存、10 CPU、约 362 GiB 可用空间。
- PATH 未找到 Go/depot_tools/GN/Ninja；只有 CommandLineTools，未发现 /Applications/Xcode.app。
- Docker CLI 已装，daemon 未运行；GoLand MCP 可用，后续单元测试经该 MCP 执行。
- 旧补丁未实现证书忽略开关，本次根据用户明确需求新增，默认关闭忽略。
- 官方 Mac Stable API 返回 159.0.8154.34，Chromium revision 4deb883708d3d25100c5aac2148aafc95dae95ac；已启动浅克隆。
- 159 已删除 native C API 与桌面 GN 目标；144.0.7559.0 仍有原生接口，使用其兼容层源码适配 159，不降级 //net 网络栈。
- 发现 GoLand 已配置本机 Go 1.27.0 SDK，可只读复用；本任务缓存和构建输出仍放项目目录。
- macOS arm64 原生库已生成；修复运行时 CommandLine/ICU 初始化、install_name 及 Buffer 在 EOF 时的所有权。
- GoLand MCP 集成终端执行 scripts/test_cronet.sh，全部测试和 -race 通过；日志 .build/logs/go-test.log。
- 增加 HTTP/2 自定义 SETTINGS 与 Chromium 原生 GREASE，抓取 TLS 内实际 HTTP/2 SETTINGS 帧通过；修复未知长度上传最后一块 n>0, EOF 被丢弃及 ContentLength=0 的标准库语义。
- macOS 格式化、许可证打包后再次通过 GoLand MCP 全量 -race 测试，日志改为 `.build/logs/go-test-mac-arm64.log`。
- Docker 构建镜像已完成；Ubuntu 包下载 502 通过缓存与整体重试恢复。Linux checkout 使用宿主 Git 准备，编译仍在容器。
- 当前 gclient 的 custom_deps=None 未跳过 GCS 测试数据，改为从固定 HEAD 生成过滤 DEPS；gsutil 提前单独初始化避免并发锁冲突。Linux LLVM/Rust 已下载，正在安装 CIPD 工具。

- Linux x64 首次 Ninja 缺少 CED 源码，已把 `src/third_party/ced/src` 加入固定依赖白名单；8 并发续跑。macOS 最终重打包后经 GoLand MCP 再次通过全量 `-race`。
- Linux x64 已生成约 35 MiB ELF64 x86-64 so，新增 8 个代理/TLS C ABI 访问器均导出；GoLand MCP 全量 `-race` 通过，日志 `.build/logs/go-test-linux-x64.log`。arm64 构建进行中。
- Linux 桌面链接需恢复 XDG 源文件并关闭 GIO；测试 Clang 包装器增加 unused-command-line-argument 兼容参数。
- TLS 旧扩展补齐后，macOS arm64 与 Linux x64 均重新构建并通过 GoLand MCP 全量 `-race`；实际 ClientHello 验证 cipher、supported_groups 与 key_share。
- Linux x64 新库 SHA256：`8c539b88ab19ab269cbe6fe6d044cdd5910ab748abe30f760af45b2134cda719`；arm64 正在构建。
- Linux arm64 新库已生成，SHA256：`8ee445af2e216a5fade768b3e408840359d1e1636c62027058ae2de4066af41f`；GoLand MCP 全量 `-race` 通过，日志 `.build/logs/go-test-linux-arm64.log`。
- 最终 macOS arm64、Linux x64、Linux arm64 三平台均完成 TLS parity 构建和测试。
