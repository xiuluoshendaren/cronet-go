# Cronet 版本升级说明

> 本文记录本项目从旧版 Cronet 144 定制库升级到 Chromium 159.0.8154.34 的完整过程、关键设计、构建方法、验证结果和注意事项。
>
> 记录日期：2026-11-26
> 对应提交：`ea996eb feat: restore legacy TLS engine parameters`
> 适用仓库：`cronet-go`
> 已验证目标：macOS arm64、Linux x86-64、Linux arm64

## 1. 升级背景

项目旧版本使用的是 Cronet 144 定制动态库。除标准 Cronet 能力外，旧库还包含以下本地定制：

- 固定代理规则；
- HTTP/HTTPS 代理账号和密码认证；
- HTTP/2 自定义 SETTINGS；
- HTTP/2 SETTINGS GREASE；
- TLS cipher suite 名称和顺序配置；
- TLS supported groups/curves 配置；
- 桌面 Linux 构建适配；
- 旧版 C ABI 及双向流接口。

升级到 159 后，首先发现下游传入的 TLS 参数没有生效。典型现象是 Chromium 打印未知 experimental option 的 WARNING，然后忽略参数。

排查结论不是“Chromium 159 的 TLS 底层不支持配置”，而是：

1. 新版源码删除了旧版桌面 C ABI；
2. 旧版定制补丁没有完整迁移到 159；
3. 旧二进制中的 `TLSCipherSuiteMapper::NamesToIds`、`TLSCurveMapper::NamesToGroupInfos` 没有进入新版构建；
4. `tls_cipher_suites`、`tls_curves` 没有对应的 experimental JSON 解析分支；
5. 参数最终落入未知参数分支，只打印 WARNING，不会自动生效。

因此，本次升级不是简单替换 `.so` 或 `.dylib`，而是同时完成：

- Chromium 网络栈升级；
- 旧 C ABI 兼容层恢复；
- 旧定制能力审计与迁移；
- Go 绑定适配；
- 三平台原生库构建；
- 真实网络行为验证。

## 2. 版本和兼容策略

### 2.1 固定版本

| 项目 | 固定值 | 用途 |
| --- | --- | --- |
| Chrome/Cronet 目标版本 | `159.0.8154.34` | 实际 Chromium 网络栈和 Cronet common |
| Chromium revision | `4deb883708d3d25100c5aac2148aafc95dae95ac` | 防止源码漂移 |
| C ABI 兼容层版本 | `144.0.7559.0` | 恢复 159 已删除的 native C ABI |
| grpc_support 兼容层版本 | `144.0.7559.0` | 恢复双向流 C 接口 |
| depot_tools revision | `ee90e3f95824aa10ed7a912fe08e16e45eb62004` | 固定同步工具行为 |
| Linux Go 测试工具链 | `go1.27.0` linux-amd64 | 固定 Linux CGO 测试环境 |

锁文件：

- `native/cronet.lock.json`：Chromium、兼容层、depot_tools、归档 URL 和 SHA256；
- `native/go-test.lock.json`：Go 测试工具链版本、文件名、大小和 SHA256。

### 2.2 不是整体降级到 144

本次只从 144 恢复已经删除的接口兼容层，主要包括：

- `components/cronet/native/`；
- `components/grpc_support/`；
- 必要的 C ABI 生成代码和桌面目标适配。

以下核心仍使用 159：

- `//net`；
- BoringSSL；
- QUIC/HTTP2/HTTP3 实现；
- Cronet common；
- 代理解析、证书校验和 socket 实现。

不能将“使用 144 兼容层”理解为整个网络栈退回 144，也不能把完整 144 源码覆盖到 159。

### 2.3 不直接套用旧 `1.patch`

旧 `1.patch` 保留作迁移依据，但不直接应用到 159，原因包括：

- 文件路径、类接口和 GN 规则已变化；
- 旧补丁不包含后来旧二进制里的 TLS mapper 定制；
- 旧补丁存在不应保留的行为，例如把代理认证内容写入 User-Agent；
- 旧随机 SETTINGS 逻辑可能使用无效区间或缺失枚举；
- 旧补丁放宽请求泄漏 CHECK，不利于发现 Go/Cronet 生命周期错误。

本项目改为由 `scripts/prepare_cronet.py` 按明确源码锚点迁移每一项能力。锚点变化时直接报错，避免“脚本执行成功但补丁没有生效”。

## 3. 最终改动总览

### 3.1 构建与补丁

| 文件 | 作用 |
| --- | --- |
| `scripts/build_cronet.py` | 固定版本同步、GN/Ninja 构建、打包和 SHA256 清单 |
| `scripts/build_linux.py` | Linux 源码复用、Docker 双架构构建 |
| `scripts/build_linux.sh` | 宿主侧 Linux 构建入口 |
| `scripts/prepare_cronet.py` | C ABI、桌面目标及全部本地定制的核心补丁脚本 |
| `scripts/patch_clt.py` | 只有 Command Line Tools 时的 macOS SDK 适配 |
| `scripts/prepare_go.py` | 下载并校验项目内 Linux Go 工具链 |
| `scripts/test_cronet.sh` | 单目标全量 `-race` 测试 |
| `scripts/test_linux.py` / `test_linux.sh` | Linux CGO 交叉编译和测试 |
| `native/Dockerfile` | Ubuntu 24.04 Linux 构建环境 |

### 3.2 原生定制

| 文件 | 作用 |
| --- | --- |
| `native/desktop_config.cc/.h` | 代理认证、显式不安全证书校验器 |
| `native/tls_cipher_suite_mapper.cc/.h` | 旧 cipher 名称到 wire ID 的映射 |
| `native/tls_curve_mapper.cc/.h` | 旧 curve 名称到 159 group 配置的映射 |
| `native/cronet_ssl_config_service.cc/.h` | 将 TLS 配置传入 Chromium `SSLContextConfig` |

### 3.3 Go 接口

| 文件 | 作用 |
| --- | --- |
| `engine_proxy.go` | 代理 URL、凭证和显式证书忽略配置 |
| `engine_http2.go` | HTTP/2 SETTINGS 合并、校验和 GREASE |
| `engine_tls.go` | TLS 名称数组合并到 experimental JSON |
| `transport.go` | `http.RoundTripper`、上传 EOF、响应和取消生命周期适配 |

## 4. 构建前准备和目录约束

### 4.1 宿主要求

macOS：

- Python 3.12 或更高版本；
- Git；
- Apple Command Line Tools 或 Xcode；
- 可用的 macOS SDK；
- `codesign`、`install_name_tool` 等系统工具。

Linux 构建：

- Docker Desktop 或兼容 Docker 环境；
- 宿主机 Git 和 Python；
- 足够磁盘空间。Chromium 源码、工具链、双架构对象文件和缓存体积很大，不能把普通 Go 项目的磁盘占用作为估算依据。

### 4.2 所有构建内容留在项目内

主要目录：

```text
.build/                 源码、depot_tools、工具链、缓存、日志、中间对象
.build/chromium/src/    macOS 构建使用的 Chromium 源码
.build/linux/           Linux 独立源码、工具链、缓存和构建环境
dist/                   最终动态库、头文件、许可证和 manifest
```

`.build/` 和 `dist/` 不纳入 Git。它们包含大量生成物，且不同机器不应复用为源码提交。

`CRONET_BUILD_ROOT` 必须位于项目 `.build/` 内，脚本会拒绝把构建目录指向项目外部。

### 4.3 代理约定

本项目本次使用：

- 宿主：`127.0.0.1:8897`；
- Docker：`host.docker.internal:8897`。

默认命令已带上述代理。不需要代理时，Python 构建入口可显式传入：

```sh
--proxy ''
```

注意区分两类代理：

1. 构建下载代理：用于 Git、HTTP 下载和 Docker 构建；
2. Cronet 运行时代理：由 `SetProxyServer` 写入引擎配置。

二者互不等价，修改构建代理不会自动改变业务请求代理。

## 5. 可复现升级和构建流程

### 5.1 第一步：确定并锁定版本

本次通过 Chrome Stable 版本信息确定 159.0.8154.34，再固定对应的 Chromium revision。

后续升级不能只把版本号改成“最新”。至少应同步更新：

- `chrome_version`；
- `chromium_revision`；
- `depot_tools_revision`；
- 兼容层归档 URL 和 SHA256；
- 必要时更新 Go 工具链锁；
- Docker 镜像标签和文档中的版本说明。

如果已有 checkout 的 HEAD 与锁文件不一致，脚本会报错。不要在旧源码目录里强行切换多个版本后继续增量补丁；建议使用独立、干净的 `.build` 目录。

### 5.2 第二步：同步 Chromium 和依赖

macOS 完整同步并构建：

```sh
python3 scripts/build_cronet.py all --cpu arm64 --jobs 8
```

只同步：

```sh
python3 scripts/build_cronet.py sync
```

只构建已完整同步的源码：

```sh
python3 scripts/build_cronet.py build --cpu arm64 --jobs 8
```

同步过程做了以下特殊处理：

1. 使用浅克隆降低历史数据量；
2. 为 tag-only clone 建立固定的本地 remote HEAD，避免 gclient 枚举全部上游引用；
3. 解析固定 revision 的 `DEPS`，跳过与 Cronet 无关的大型浏览器和测试数据；
4. 显式保留 LLVM、Rust、BoringSSL、ICU、QUICHE、CED 等真实构建依赖；
5. 先串行初始化 CIPD/gsutil，避免多个并发包装器争抢同一初始化锁；
6. 生成 `LASTCHANGE`；
7. 所有缓存放入项目目录。

重要：当前 gclient 不能可靠地通过 `custom_deps=None` 跳过所有 GCS/CIPD 条目，因此脚本还直接过滤固定 `DEPS` 中对应字典值。未来升级 depot_tools 后应重新确认该行为，不要盲目删除过滤逻辑。

### 5.3 第三步：执行源码适配

`prepare_cronet.py` 在每次构建前执行，主要步骤为：

1. 校验 Chromium HEAD 必须等于锁定 revision；
2. 修改根 GN 配置，避免桌面 Cronet 引入 ANGLE；
3. 恢复 144 native C ABI 和 grpc_support；
4. 扩展 IDL、生成头文件、结构体和访问器；
5. 恢复桌面 shared library 目标；
6. 注入代理、认证、证书开关和 HTTP/2 配置；
7. 注入 TLS 配置解析、mapper、SSLConfigService 和 BoringSSL 有序 cipher API；
8. 将本地 `.cc/.h` 加入对应 GN 目标；
9. 格式化相关 GN 文件。

脚本采用“唯一锚点替换”。常见错误是上游升级后锚点不再唯一或已经改变。此时应阅读新源码并更新适配，不应通过降低校验、全局模糊替换来绕过错误。

### 5.4 第四步：先构建并验证 macOS

```sh
python3 scripts/build_cronet.py build --cpu arm64 --jobs 8
./scripts/test_cronet.sh mac-arm64
```

本项目约定单元测试通过 GoLand MCP 集成终端执行。

macOS 打包额外执行：

- 将 dylib install name 设置为 `@rpath/libcronet.dylib`；
- 对 dylib 做 ad-hoc codesign；
- 复制配套 C 头文件；
- 生成 Chromium 和第三方许可证；
- 生成逐文件 SHA256 `manifest.json`。

只有 macOS 构建和测试通过后，才继续 Linux 双架构构建。这样可先在较简单的原生环境中发现 C++ 编译、链接和运行时问题，避免同时在两个交叉目标上排查同一错误。

### 5.5 第五步：构建 Linux x64/arm64

标准入口：

```sh
./scripts/build_linux.sh --cpu x64 --jobs 8
./scripts/build_linux.sh --cpu arm64 --jobs 8
```

也可一次构建两个目标：

```sh
./scripts/build_linux.sh --cpu all --jobs 8
```

实现方式：

- 构建容器固定为 Ubuntu 24.04 linux/amd64；
- x64 直接编译；
- arm64 在 linux/amd64 构建容器中交叉编译；
- 使用 Chromium 固定的 bullseye amd64/arm64 sysroot；
- 使用项目内 LLVM、LLD、GN、Ninja 和 Rust 工具链；
- 通过 Git alternates 复用宿主机已有、不可变的 Git 对象；
- Linux checkout 与 macOS checkout 分离，避免构建目录和补丁状态互相污染。

注意：Git alternates 中记录的是绝对路径，因此 Docker 挂载项目时必须保持与宿主相同的绝对路径。现有脚本使用：

```sh
-v "$TASK_ROOT:$TASK_ROOT" -w "$TASK_ROOT"
```

不要随意改成只挂载到 `/src`，否则复用的 Git 对象路径可能失效。

### 5.6 已完成同步后的增量构建

如果源码和依赖已经确认完整，可在容器内直接执行 `build`，跳过昂贵的重复 sync：

```sh
docker run --rm --platform linux/amd64 \
  --entrypoint python3 \
  -v "$PWD:$PWD" -w "$PWD" \
  -e HOME="$PWD/.build/linux/home" \
  -e TMPDIR="$PWD/.build/tmp" \
  -e CRONET_BUILD_ROOT=.build/linux \
  cronet-go-builder:159 \
  scripts/build_cronet.py build \
  --cpu x64 --proxy http://host.docker.internal:8897 --jobs 8
```

将 `--cpu x64` 改成 `--cpu arm64` 即可构建 arm64。

只能在“固定 revision 正确、依赖完整、此前 sync 已成功”的前提下使用此方式。全新环境不能跳过 sync。

## 6. C ABI 和桌面运行时适配

### 6.1 恢复旧 C ABI

159 已删除项目依赖的 native C API。恢复时不能只复制一个头文件，必须同时保持以下内容一致：

- `cronet.idl`；
- `cronet.idl_c.h`；
- `cronet.idl_impl_struct.h`；
- `cronet.idl_impl_struct.cc`；
- engine 创建和参数复制逻辑；
- GN sources/deps；
- Go CGO 声明与调用。

新增字段必须贯穿整个链路。例如代理字段不是只加 Go setter，而是：

```text
Go EngineParams
  -> C ABI setter
  -> Cronet_EngineParams 结构体
  -> native engine.cc
  -> URLRequestContextConfig
  -> CronetContext / URLRequestContextBuilder
  -> Chromium 网络组件
```

只修改其中一层，常见结果是编译失败、参数被忽略或 ABI 不一致。

### 6.2 桌面 shared library

本次恢复了非 Android 的 `shared_library("cronet")` 目标，并处理：

- 桌面 POSIX path/proxy helper；
- Linux XDG 源文件；
- 不需要的 Android JNI 和流量标记；
- Linux GIO、GTK、DBus、X11、Aura、Ozone 等桌面浏览器依赖关闭；
- grpc_support 双向流目标；
- Cronet common 与恢复 ABI 的链接关系。

GN 中可能出现某个旧开关在当前版本“没有作用”的 WARNING，例如 `use_gtk`。这类 WARNING 应与真正编译/链接错误区分，但后续升级仍应清理失效参数。

### 6.3 CommandLine 和 ICU 初始化

桌面动态库不能假设宿主已经初始化 Chromium 全局状态。本次补充：

- `base::CommandLine` 未初始化时进行初始化；
- ICU 初始化并检查结果；
- FeatureList 初始化。

缺少这些初始化时，库可能编译成功，却在创建引擎或首次请求时触发 CHECK、崩溃或功能异常。因此“能链接”不是运行时验证的替代品。

## 7. 旧扩展参数迁移结果

### 7.1 代理规则

支持：

- HTTP 代理；
- HTTPS 代理；
- SOCKS4/SOCKS5；
- Chromium 分协议代理规则和回退规则。

Go 示例：

```go
if err := params.SetProxyServer("http://127.0.0.1:8897"); err != nil {
    panic(err)
}
```

带账号密码：

```go
if err := params.SetProxyServer("http://user:password@127.0.0.1:8080"); err != nil {
    panic(err)
}
```

也可分开设置：

```go
params.SetProxyCredentials("user", "password")
```

注意事项：

- URL 中特殊字符应进行 URL 编码；
- 非法 scheme、端口、路径、query、fragment 和控制字符会被拒绝；
- 错误信息不主动回显原始带密码 URL；
- 认证信息不会写入 `ProxyRules()` 返回值；
- 显式代理规则会应用到 loopback，本地测试也可能经过代理；
- 清空代理规则恢复 Chromium 默认代理配置；
- `SetProxyServer` 现在返回 `error`。普通函数调用语句仍可编译，但绑定函数类型或实现旧接口时需要更新签名。

### 7.2 代理认证

旧补丁曾把 Basic 认证内容借道 User-Agent 传递。本次改为独立生成 `Proxy-Authorization`：

- 用于 HTTP 407 认证；
- 用于 HTTPS CONNECT 建隧道；
- 只发送给代理；
- 不修改源站 User-Agent；
- 不把代理凭证转发给源站。

限制：Chromium 当前路径不支持带账号认证的 SOCKS4/SOCKS5 配置。Go 层会直接返回错误，不静默丢弃 SOCKS 凭证。

### 7.3 证书校验开关

默认行为是正常校验证书。只有显式调用以下接口才关闭：

```go
params.SetIgnoreCertificateErrors(true)
```

该开关影响此引擎请求及 HTTPS 代理的证书校验。

安全注意：

- 不要在生产环境默认开启；
- 开启后会失去正常证书身份认证保护；
- 自签证书测试通过不代表默认校验被关闭，测试同时验证默认拒绝自签证书；
- 旧补丁中未完成的证书忽略代码不能直接照搬，本次使用 159 的 `CertVerifier` 接口实现。

### 7.4 HTTP/2 SETTINGS 和 GREASE

Go 接口：

```go
if err := params.SetHTTP2Settings(map[uint16]uint32{
    6: 300000,
}, true); err != nil {
    panic(err)
}
```

行为：

- `settings` 只覆盖显式给出的 setting；
- 未提供的 setting 保留 Chromium 默认值；
- 第二个参数显式控制每连接 SETTINGS GREASE；
- 使用 Chromium 原生 GREASE 实现；
- 已验证 TLS 连接内实际发送的 SETTINGS 帧。

参数校验包括：

- setting 2 不允许启用 server push，只能为 0；
- setting 4 不得超过 `2^31-1`；
- setting 5 必须在 `[16384, 16777215]`；
- setting 8、9 只能为 0 或 1。

注意：

- SETTINGS 的发送顺序遵循 Chromium 的 SettingsMap，本 API 不承诺任意顺序；
- GREASE 值每连接随机，测试不能写死；
- 不迁移旧版随机区间反置、无效随机 setting 等逻辑；
- HTTP/2 仍需单独启用，设置 OPTIONS 不等于自动启用协议。

### 7.5 不迁移的旧行为

以下行为有意不保留：

- 把代理认证写入 User-Agent；
- 放宽请求泄漏 CHECK；
- 随机生成无效 HTTP/2 setting；
- 用旧源码大面积覆盖新网络栈。

请求泄漏问题通过修正 Go 请求、回调、Buffer 和取消生命周期解决，而不是关闭检查。

## 8. TLS 参数恢复专题

这是本次升级中最容易遗漏的部分。

### 8.1 配置入口

支持 experimental JSON 顶层字段：

```json
{
  "tls_cipher_suites": [
    "TLS_CHACHA20_POLY1305_SHA256",
    "TLS_AES_128_GCM_SHA256",
    "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
  ],
  "tls_curves": ["P-256", "X25519", "P-384"]
}
```

Go 辅助方法：

```go
if err := params.SetTLSCipherSuites([]string{
    "TLS_AES_128_GCM_SHA256",
    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
}); err != nil {
    panic(err)
}

if err := params.SetTLSCurves([]string{"X25519", "P-256"}); err != nil {
    panic(err)
}
```

调用顺序注意事项：

- 必须在引擎启动前设置；
- 辅助方法会合并当前 experimental JSON，保留已有 QUIC、HTTP2 等字段；
- 当前 experimental JSON 必须是 JSON object，否则辅助方法返回错误；
- 辅助方法之后再调用 `SetExperimentalOptions` 会整体覆盖 JSON，可能删除刚设置的 TLS 字段；
- 建议统一先写基础 JSON，再调用辅助方法，或直接在最终 JSON 中包含 TLS 字段；
- `NewCronetTransport` 会接管并释放 params，不要在交给 transport 后继续使用该对象。

### 8.2 原生处理链路

完整链路如下：

```text
experimental_options JSON
  -> 解析 tls_cipher_suites / tls_curves 字符串数组
  -> 从通用 experimental 字典移除这两个键
  -> TLSCipherSuiteMapper::NamesToIds
  -> TLSCurveMapper::NamesToGroupInfos
  -> CronetSSLConfigService
  -> net::SSLContextConfig
  -> SSLClientSocketImpl
  -> BoringSSL SSL_set_cipher_list_with_order / supported groups
  -> ClientHello
```

“从通用字典移除”很重要：已识别的本地扩展不能继续落入上游未知参数循环，否则仍会出现误导性的未知参数 WARNING。

数组只接受字符串项。非字符串项会打印 WARNING 并忽略，不会尝试把数字或其他对象转换成名称。

### 8.3 Cipher 映射规则

旧表中的名称和 wire value 均保留，包括旧 `TLS_GREASE` 占位名。

通用规则：

- 忽略名称首尾空白；
- 名称大小写不敏感；
- 未知名称打印 WARNING 并忽略；
- 空数组、`nil` 或所有名称都未识别时，保留 Chromium 默认配置；
- `TLS_GREASE` 不直接写入 cipher 列表，由 159 自动生成 GREASE；
- 旧表中已知、但当前 BoringSSL 已不支持的 cipher，会在最底层忽略；
- 配置非空，但过滤后完全没有可用 cipher 时，握手明确失败，不伪造 wire ID，也不悄悄退回一套不相关配置。

BoringSSL 159 分开保存 TLS 1.3 和 TLS 1.2 cipher：

- TLS 1.3 在 ClientHello 中固定先于 TLS 1.2；
- 每个协议组内部严格按配置顺序排列；
- 不能把 TLS 1.2 cipher 插入 TLS 1.3 cipher 前面来实现跨协议任意排序；
- 测试和调用方都不应假设整个列表可以跨协议任意混排。

### 8.4 Curve/supported groups 映射

支持：

| 名称 | 结果 |
| --- | --- |
| `X25519MLKEM768` | 支持，并标记可发送 key share |
| `X25519` | 支持，并标记可发送 key share |
| `P-256` / `SECP256R1` | 支持 |
| `P-384` / `SECP384R1` | 支持 |

无法恢复：

- `X25519KYBER768`；
- `X25519KYBER768DRAFT00`。

原因：159 对应 BoringSSL 已删除这些 draft Kyber group 实现。当前行为是打印 WARNING 并忽略，而不是映射到 ML-KEM 或伪造旧 group ID。

注意：`X25519MLKEM768` 不是 draft Kyber 的简单改名。若要模拟旧 wire 行为，不能用新算法冒充旧算法。

### 8.5 GREASE 对测试的影响

159 默认可能自动生成：

- cipher GREASE；
- supported_groups GREASE；
- key_share GREASE。

因此：

- 不要断言 ClientHello 第一项永远是配置的 cipher/group；
- 不要写死 GREASE 值；
- 比较顺序时应先识别并过滤 GREASE；
- 也不要把 GREASE 当成“配置未生效”或“多出了未知 cipher”。

### 8.6 `enable_cookie_store` 结论

核查结果：

- 旧定制库没有该参数字符串；
- 旧版明确 `SetCookieStore(nullptr)`；
- 159 对应路径也明确禁用原生 CookieStore；
- 没有充分证据表明旧版实际支持此 experimental 参数。

因此本次没有伪造 `enable_cookie_store` 解析分支。下游不应继续传这个字段并期待生效；需要 Cookie 管理时，可在 Go `http.Client` 层使用 `http.CookieJar`。

## 9. Go 传输层和生命周期修复

升级原生库后，还修复了若干与版本替换无直接关系、但会被新检查和测试暴露的问题。

### 9.1 Buffer 所有权

基本规则：

- Buffer 创建并成功交给 Cronet 后，由 Cronet 接管；
- 只有在对应 `OnReadCompleted` 等回调交还时，Go 才能按约定处理；
- EOF、失败和取消路径不得重复释放；
- 不得因 Go 侧已读到 EOF 就额外释放仍归 Cronet 的 Buffer。

否则可能出现 double free、use-after-free、请求泄漏 CHECK 或偶发崩溃。

### 9.2 未知长度上传的最后一块

上传 Reader 可能合法返回：

```go
n > 0, err == io.EOF
```

这表示“本缓冲区有数据，并且之后没有数据”，不是“丢弃本缓冲区”。本次修复为：

- 先递交最后的 `n` 字节；
- 再以 `isLast=true` 完成写入；
- 不再因同时出现 EOF 而丢掉末块。

### 9.3 `ContentLength == 0`

按照 Go `net/http` 语义，0 不能简单等价于“没有任何 body”，还涉及未知长度和传输行为。本次按标准库语义调整，避免 Cronet transport 与 `http.Transport` 在空 body/未知长度场景下产生不一致。

### 9.4 取消和资源回收

测试覆盖请求取消，确保：

- Cronet request 正确取消；
- callback、executor 和 buffer 不泄漏；
- transport 关闭顺序正确；
- race detector 下无数据竞争。

## 10. 测试和验收

### 10.1 测试原则

单元测试必须通过 GoLand MCP 集成终端执行。测试使用本地 HTTP/TLS/代理服务，不依赖固定外部网站。

测试脚本：

```sh
./scripts/test_cronet.sh mac-arm64
```

Linux 可使用仓库双架构测试入口：

```sh
./scripts/test_linux.sh --cpu x64
./scripts/test_linux.sh --cpu arm64
```

或：

```sh
./scripts/test_linux.sh --cpu all
```

### 10.2 防止误用旧库

`test_cronet.sh` 将动态库 SHA256 加入 Go 链接 build ID：

```text
-ldflags="-buildid=<动态库 SHA256>"
```

这是必要的。仅替换 `.so/.dylib` 不一定能可靠使所有 Go 构建缓存失效，否则可能出现“源码和库已更新，但测试仍链接旧库”的假阳性或假阴性。

### 10.3 覆盖范围

测试覆盖：

- 实际 Cronet 引擎版本；
- 代理参数解析；
- HTTP 代理认证；
- HTTPS CONNECT 认证；
- 凭证不泄漏到源站；
- 默认拒绝自签证书；
- 显式忽略证书错误；
- 实际 ClientHello cipher 顺序；
- 实际 supported_groups 和 key_share；
- HTTP/2；
- 自定义 SETTINGS 和 GREASE 实际帧；
- 重复大响应；
- 未知长度上传末块；
- 请求取消；
- Go race 检查。

TLS 参数测试不是只检查 JSON 字符串，而是启动本地 TCP listener，读取真实 ClientHello 并解析扩展。

### 10.4 预期中的握手错误日志

部分测试会主动制造握手失败：

- ClientHello 捕获测试只读取握手包，不完成 TLS 服务端的握手；
- 默认证书校验测试使用自签证书并预期失败。

因此日志中可能出现 `handshake failed`、`unknown certificate` 等 ERROR。判断测试成功应以最终 `PASS`、进程退出码和测试名称为准，不能看到单条 ERROR 就认定失败。

### 10.5 本次最终结果

| 目标 | 动态库 | GoLand MCP 全量 `-race` | 测试日志 |
| --- | --- | --- | --- |
| macOS arm64 | `dist/mac-arm64/libcronet.dylib` | PASS | `.build/logs/go-test-mac-arm64.log` |
| Linux x86-64 | `dist/linux-x64/libcronet.so` | PASS | `.build/logs/go-test-linux-x64.log` |
| Linux arm64 | `dist/linux-arm64/libcronet.so` | PASS | `.build/logs/go-test-linux-arm64.log` |

本次动态库 SHA256：

| 目标 | SHA256 |
| --- | --- |
| macOS arm64 | `ead5c6f15735059b837d4ef359c7fa96bd7845ad8a62353ed35da71e03cd56ac` |
| Linux x86-64 | `8c539b88ab19ab269cbe6fe6d044cdd5910ab748abe30f760af45b2134cda719` |
| Linux arm64 | `8ee445af2e216a5fade768b3e408840359d1e1636c62027058ae2de4066af41f` |

这些哈希只对应本文记录的本次构建。后续重新编译、修改补丁或更换工具链后应以新 `manifest.json` 为准，不要继续把旧哈希当作预期值。

## 11. 产物检查和下游接入

### 11.1 架构检查

macOS：

```sh
file dist/mac-arm64/libcronet.dylib
```

Linux：

```sh
file dist/linux-x64/libcronet.so
readelf -h dist/linux-x64/libcronet.so

file dist/linux-arm64/libcronet.so
readelf -h dist/linux-arm64/libcronet.so
```

预期：

- macOS：arm64 Mach-O dynamic library；
- Linux x64：ELF64、X86-64；
- Linux arm64：ELF64、AArch64。

### 11.2 符号检查

macOS：

```sh
nm -C dist/mac-arm64/libcronet.dylib | grep -E \
  'TLSCipherSuiteMapper::NamesToIds|TLSCurveMapper::NamesToGroupInfos|SSL_set_cipher_list_with_order'
```

Linux：

```sh
nm -C dist/linux-x64/libcronet.so | grep -E \
  'TLSCipherSuiteMapper::NamesToIds|TLSCurveMapper::NamesToGroupInfos|SSL_set_cipher_list_with_order'
```

注意：这些内部符号在当前构建中可能不是动态导出符号，因此 `nm -D` 查不到并不代表未编译进去。本次使用完整符号表 `nm -C` 验证。

符号存在只能证明代码进入产物，不能证明参数解析和实际握手正确，仍必须运行 ClientHello 测试。

### 11.3 manifest 校验

每个 `dist/<平台>/manifest.json` 包含：

- Chrome 版本和 Chromium revision；
- 兼容层版本和归档 SHA256；
- 目标 OS/CPU；
- 动态库、头文件、版本、许可证的逐文件 SHA256。

交付前应重新计算并比对，不应只检查文件是否存在。

### 11.4 下游 CGO 配置

macOS 示例：

```sh
export CGO_ENABLED=1
export CGO_CFLAGS="-I$PWD/dist/mac-arm64/include"
export CGO_LDFLAGS="-L$PWD/dist/mac-arm64 -lcronet -Wl,-rpath,$PWD/dist/mac-arm64"
```

Linux 将目录替换为：

```text
dist/linux-x64
```

或：

```text
dist/linux-arm64
```

注意：

- 头文件和动态库必须来自同一次构建；
- 不得混用 macOS/Linux 库；
- 不得混用 x64/arm64 库；
- 不得用旧 144 头文件搭配新库，或新头文件搭配旧库；
- 部署机器需要能找到动态库，rpath、工作目录和最终安装布局必须一起检查；
- 下游若已经通过 `SetExperimentalOptions` 写入 `tls_cipher_suites`、`tls_curves`，无需为了新辅助方法强行改代码；
- 下游若仍传 `enable_cookie_store`，应删除该无效字段并改用 Go CookieJar。

## 12. 本次实际遇到的问题和处理

### 12.1 新版缺少旧 C ABI 和桌面目标

现象：159 中相关 native 文件和桌面构建入口已删除。

处理：只恢复 144 的接口兼容层并适配 159，不回退整个网络栈。

### 12.2 macOS 只有 Command Line Tools

现象：上游脚本默认按完整 Xcode.app 获取版本、SDK 和工具路径。

处理：`patch_clt.py` 增加 CLT 的 pkg 版本、SDK 路径、构建版本和工具路径识别。仍需要有效 macOS SDK，不能在没有 Apple SDK 的环境中构建 dylib。

### 12.3 gclient 同步大型挂载目录缓慢或停滞

现象：Docker 绑定挂载的大型 Chromium 工作区执行 Git 检查非常慢，可能停在类似 `git diff ... -G Subproject commit` 的阶段。

处理：

- 源码准备优先使用宿主 Git；
- 使用浅克隆、固定 remote HEAD 和 Git alternates；
- 确认源码和依赖已经完整后，增量编译只执行 `build`，不重复 `sync`；
- 不要在依赖尚未完整时把跳过 sync 当作通用解决方案。

### 12.4 GCS/CIPD 测试数据被意外下载

原因：`custom_deps=None` 没有覆盖全部 GCS/CIPD 条目。

处理：从固定 `DEPS` AST 中定位并替换被跳过条目，同时保留 Cronet 编译实际需要的工具链和网络依赖。

### 12.5 CIPD/gsutil 并发初始化冲突

处理：提前串行执行 CIPD ensure 和 gsutil 初始化，再进入并发同步，避免多个进程同时初始化相同包装器和锁。

### 12.6 Ubuntu 包下载 502

处理：Dockerfile 使用 apt cache mount、下载重试和整体重试。遇到镜像源临时 5xx 时先保留缓存重试，不要立即更换整个构建版本或工具链。

### 12.7 Linux 缺少 CED 源码

现象：Ninja 编译需要 `src/third_party/ced/src`，过度裁剪依赖后文件缺失。

处理：将 CED 加入固定保留白名单。教训是“Cronet 不需要完整浏览器”不等于可以删除所有看似无关的 `third_party` 包；应由真实编译依赖决定。

### 12.8 Linux 桌面链接和测试编译参数

处理：

- 恢复必要的 XDG 源文件；
- 关闭 GIO 等非必要桌面依赖；
- CGO Clang 包装器增加目标三元组、sysroot、LLD；
- 增加 `-Wno-unused-command-line-argument` 兼容测试编译参数。

### 12.9 历史补丁导致重复 struct 字段

现象：分阶段执行旧补丁后，`proxy_rules`、`proxy_username`、`proxy_password`、`ignore_certificate_errors` 被插入两次，最终 C++ 编译报 duplicate member。

处理：当前 `prepare_cronet.py` 会先清理历史四字段块，再应用完整块；新实现可幂等续建。

注意：

- 不要只修当前生成的 `.build` 文件而不修补丁脚本，否则下次干净构建会复发；
- 不要反复手工追加字段；
- 如果源码树已有多轮不可确认的手工修改，优先换成干净 checkout；
- 幂等不等于可以掩盖所有上游冲突，锚点不明确时仍必须报错。

### 12.10 TLS 参数 WARNING 但不生效

原因：新版没有解析分支和 mapper，不是 BoringSSL 完全没有 TLS 配置能力。

处理：恢复完整原生链路，并用真实 ClientHello 验证，而不是仅确认 Go JSON 已写入。

## 13. 后续再次升级的注意事项

后续升级到更新 Chromium 时，建议严格按以下清单执行。

### 13.1 升级前审计

- [ ] 记录当前版本、revision、动态库哈希和可用配置样例；
- [ ] 阅读 `1.patch`，但不要假设它包含全部旧二进制定制；
- [ ] 检查旧库符号、字符串和实际 ClientHello，建立行为基线；
- [ ] 盘点下游所有 `EngineParams` 和 experimental JSON 字段；
- [ ] 阅读新 Chromium 的 C ABI、GN、SSLConfigService、BoringSSL API；
- [ ] 确认 144 兼容层是否仍适合，不能机械沿用；
- [ ] 明确无法支持的参数及理由，不静默映射为其他算法。

### 13.2 锁和依赖

- [ ] 更新并核对所有版本锁和 SHA256；
- [ ] 检查 depot_tools/gclient 行为变化；
- [ ] 重新验证 DEPS 裁剪白名单；
- [ ] 不删除编译实际需要的 LLVM、Rust、ICU、CED 等依赖；
- [ ] 使用独立干净构建目录验证一次完整 sync；
- [ ] 确认所有缓存、日志和临时文件仍在项目内。

### 13.3 补丁和 ABI

- [ ] 每个补丁锚点都能唯一匹配；
- [ ] IDL、生成头、结构体、实现、engine 和 Go 绑定同步更新；
- [ ] GN sources/deps 包含全部新增文件；
- [ ] 连续执行两次 prepare，确认不会重复插入；
- [ ] 检查代理凭证只发送到代理；
- [ ] 默认证书校验保持开启；
- [ ] 不用关闭 CHECK 代替修复生命周期问题。

### 13.4 TLS 和协议行为

- [ ] 验证 `tls_cipher_suites` 和 `tls_curves` 不再进入未知参数分支；
- [ ] 检查新 BoringSSL 是否删除或新增 cipher/group；
- [ ] 验证 TLS 1.3 与 TLS 1.2 各自顺序；
- [ ] 验证 supported_groups 和 key_share，而不只是配置对象；
- [ ] 测试过滤随机 GREASE；
- [ ] 重新评估 draft Kyber/ML-KEM，不做错误等价映射；
- [ ] 验证 HTTP/2 SETTINGS 合法性和实际发送帧；
- [ ] 空配置、未知名称、无可用 cipher 等边界均有明确行为。

### 13.5 构建和验收顺序

- [ ] 先构建 macOS arm64；
- [ ] 运行 macOS 全量 `-race`；
- [ ] 再构建 Linux x64；
- [ ] 运行 Linux x64 全量 `-race`；
- [ ] 再构建 Linux arm64；
- [ ] 运行 Linux arm64 全量 `-race`；
- [ ] 检查 `file`、`readelf`、必要符号；
- [ ] 检查三平台 manifest 和 SHA256；
- [ ] 在与下游相同的 CGO 头文件、rpath 和部署布局下复验；
- [ ] 更新 README、native 文档、本说明、计划和项目记忆；
- [ ] 审查暂存内容和敏感信息后再提交。

## 14. 安全和维护红线

1. **不要默认关闭证书校验。** 不安全校验器只能由显式参数开启。
2. **不要把代理凭证写入 User-Agent 或源站请求。** 认证必须限定在代理链路。
3. **不要伪造不支持的 TLS 算法。** draft Kyber 删除后不能映射到 ML-KEM 冒充。
4. **不要只凭编译成功宣告升级成功。** 必须验证真实 ClientHello、SETTINGS、证书和代理行为。
5. **不要混用不同版本的头文件和动态库。** C ABI 扩展要求二者严格配套。
6. **不要关闭请求泄漏 CHECK 来消除报错。** 应修复 Buffer、request、callback 和取消路径。
7. **不要提交 `.build`、`dist`、缓存或真实凭证。** 测试只能使用本地服务和测试专用假凭证。
8. **不要把当前产物哈希当成永久常量。** 每次构建后以 manifest 为准。
9. **不要让测试缓存掩盖旧库。** 保留动态库哈希参与链接 build ID 的机制。
10. **不要将本地补丁改成模糊全局替换。** 上游变化必须显式审查，避免静默漏迁移。

## 15. 结论

本次升级最终实现了：

- Chromium 159.0.8154.34 网络栈；
- 144 C ABI/grpc_support 兼容层适配；
- 代理、认证、显式证书开关、HTTP/2 SETTINGS/GREASE 迁移；
- 旧 TLS cipher/curve 配置入口恢复；
- Go 参数合并和传输层生命周期修复；
- macOS arm64、Linux x86-64、Linux arm64 三平台构建；
- 三平台 GoLand MCP 全量 `-race` 测试通过；
- 真实 ClientHello 和 HTTP/2 SETTINGS 行为验证；
- 完整头文件、许可证和 SHA256 manifest 打包。

其中最关键的验收标准是：**下游参数不仅“能设置”，而且必须能在真实网络握手中观察到预期效果。**
