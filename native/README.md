# Chromium 159 桌面 Cronet

`cronet.lock.json` 固定 2026-11-25 查询到的官方 Mac Stable Chrome
159.0.8154.34、Chromium revision、depot_tools revision 和兼容层归档的 SHA256。
这是一组经验证的固定输入；再次构建不会自动漂移到另一个版本。

Chromium 159 已删除桌面 Cronet C API 和 grpc_support。本项目恢复
144.0.7559.0 的 C ABI / grpc 适配层，再适配 159 的接口；Cronet common、TLS、
HTTP/2、QUIC 和 `//net` 均使用 159 的源码。原来的 `1.patch` 保留作为迁移依据，
不直接应用于新源码。

## 构建

macOS 需要 Apple Command Line Tools 或 Xcode、Python 3.12+、Git。Docker
Desktop 需要运行中。源码、工具、构建缓存与日志均位于项目的 `.build/`；输出位于
`dist/`，不修改系统安装路径或全局 Git 配置。

```sh
python3 scripts/build_cronet.py all --cpu arm64 --jobs 8
./scripts/build_linux.sh
```

macOS 默认代理为 `http://127.0.0.1:8897`，`--proxy ''` 可关闭代理。
Docker 使用 `host.docker.internal:8897` 访问同一宿主代理。Chromium 固定的 Linux
Rust 工具链仅提供 x86-64 版本，因此容器使用 amd64 工具链，分别交叉编译
x64 和 arm64；Apple Silicon 上由 Docker 运行 amd64 构建容器。单独构建可用：

```sh
./scripts/build_linux.sh --cpu x64 --jobs 4
./scripts/build_linux.sh --cpu arm64 --jobs 4
```

Linux 使用独立的 `.build/linux/chromium/src`，通过 Git alternates 复用 macOS
checkout 的不可变对象；二者工作目录和编译工具独立。不要单独移动其中一个源码目录。
只下载 Cronet 目标所需依赖，不获取浏览器测试数据、V8、Skia 或 Android SDK。

构建器每次检查锁定的 Chromium revision。`prepare_cronet.py` 恢复兼容层，并通过
唯一的源码锚点应用定制；上游 API 改变导致锚点不匹配时直接报错，避免静默漏补丁。
IDL、生成的 C 声明、结构成员和访问器同步扩展。

## 旧补丁迁移

| `1.patch` 内容 | 159 实现 |
| --- | --- |
| 固定代理规则 | 引擎级 `proxy_rules`，支持 HTTP、HTTPS、SOCKS4/5 和 Chromium 分协议规则 |
| 账号、密码字段 | IDL 与 C ABI 一致；HTTP 407 认证及 CONNECT 认证，仅发送给代理 |
| 将 User-Agent 写作代理认证 | 独立生成 Basic 认证头，保留真实 User-Agent |
| 自定义、随机 HTTP/2 SETTINGS | `SetHTTP2Settings` 配置具体值；可选 Chromium 原生随机 SETTINGS GREASE |
| 随机区间反置、缺失 SETTINGS 枚举 | 使用有效的 uint16 setting ID、uint32 值，不引入缺失的枚举 |
| Linux 桌面目标 | 恢复独立 shared_library 目标，关闭 Android 专用 JNI/流量标记 |
| 关闭请求泄漏 CHECK | 保留上游检查；修复 Go 请求、回调和响应 Buffer 的释放路径 |
| SSL 忽略 | 新增显式 `SetIgnoreCertificateErrors(true)`，默认正常验证 |

### 旧二进制 TLS 扩展

这些定制不在 `1.patch` 中，但旧 `libcronet.144.0.7506.0.so` 的符号和配置解析路径
明确包含它们。159 已恢复完整入口：experimental JSON 解析、两个 mapper、
`CronetSSLConfigService`、`SSLContextConfig`、socket 和 BoringSSL 有序 cipher API。

| 旧参数 | 159 支持 |
| --- | --- |
| `tls_cipher_suites` | 支持旧表全部名称；非空数组控制 TLS 1.2/1.3 cipher 及各自顺序 |
| `tls_curves` | 支持 `X25519MLKEM768`、`X25519`、`P-256`/`SECP256R1`、`P-384`/`SECP384R1` |
| `X25519KYBER768`、`X25519KYBER768DRAFT00` | 无法支持：159 BoringSSL 已删除 draft Kyber 实现；打印 WARNING 并忽略 |
| `enable_cookie_store` | 旧库无此参数且旧版明确禁用 CookieStore；159 保持禁用，可用 Go `http.CookieJar` |

名称忽略首尾空白、大小写不敏感；未知名称打印 WARNING 并忽略。`TLS_GREASE` 是旧
占位名，不进入 cipher 列表；159 的 `SSL_CTX` 已默认启用每连接 GREASE，
supported_groups 和 key_share 也可能自动带 GREASE。空数组或所有名称均未识别时保留
Chromium 默认配置。BoringSSL 在 ClientHello 中固定先写 TLS 1.3、
后写 TLS 1.2，每个协议组内部严格遵循配置顺序。

旧 cipher 名称和值完整保留在 `tls_cipher_suite_mapper.cc`。当前 BoringSSL 已删除的
cipher 会在最底层忽略，不会伪造 wire ID；过滤后没有可用 cipher 时握手明确失败。Go 辅助方法 `SetTLSCipherSuites`、
`SetTLSCurves` 只合并 JSON；直接调用 `SetExperimentalOptions` 也能生效。

HTTP/2 SETTINGS 的发送顺序遵循 Chromium 的 SettingsMap；本 API 不承诺任意顺序。
GREASE 每连接随机生成，默认关闭。SOCKS 账号认证不受 Chromium 支持，含账号的 SOCKS
URL 会返回错误。显式代理规则会应用到 loopback 主机；清空代理规则恢复 Chromium
默认代理配置。

`SetProxyServer` 现在返回 `error`，非法 URL 不会被静默接受。普通调用语句仍可编译；
绑定该方法的函数类型或实现接口时需更新签名。原生库必须与本次生成的头文件配套使用。

## 产物与验证

每个 `dist/<系统>-<CPU>/` 包含动态库、C 头文件、版本、Chromium 许可证、目标实际
依赖的第三方许可证及逐文件 SHA256 清单 `manifest.json`。

构建日志：`.build/logs/macos-build.log`、`docker-image.log`、`linux-build.log`、
`linux-arm64-build.log`。
通过 GoLand MCP 的集成终端调用 `scripts/test_cronet.sh <目标>` 运行单测；脚本使用
`-race -count=1`，并将动态库 SHA256 加入 Go 链接标识，避免误用旧库缓存。
单测使用本地 HTTP/TLS/代理服务，不依赖外部站点。

测试覆盖：实际 Cronet 版本、代理参数、HTTP 与 CONNECT 认证、凭证不泄漏到源站、
TLS 默认拒绝自签证书及显式忽略、实际 ClientHello cipher/supported_groups/key_share
顺序、HTTP/2、自定义 SETTINGS 与 GREASE 的实际发送帧、重复大响应、未知长度上传的
末块和请求取消。

本次三平台均通过 GoLand MCP 全量 `-race` 测试。动态库 SHA256：

| 产物 | SHA256 |
| --- | --- |
| `dist/mac-arm64/libcronet.dylib` | `ead5c6f15735059b837d4ef359c7fa96bd7845ad8a62353ed35da71e03cd56ac` |
| `dist/linux-x64/libcronet.so` | `8c539b88ab19ab269cbe6fe6d044cdd5910ab748abe30f760af45b2134cda719` |
| `dist/linux-arm64/libcronet.so` | `8ee445af2e216a5fade768b3e408840359d1e1636c62027058ae2de4066af41f` |

已有 `examples/cronet/` 及 `examples/libcronet.dylib` 为历史产物；新构建不会覆盖它们。
示例包含固定外部目标与代理配置，验证时使用自动化测试。
