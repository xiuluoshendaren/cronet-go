# cronet-go

将 Chromium Cronet 网络栈编译为 Go 可调用的 `.dylib` / `.so`，提供 C API
绑定、`http.RoundTripper` 和双向流接口。

当前构建固定 Chrome **159.0.8154.34**（2026-11-25 官方 Mac Stable）。Chromium
159 的网络栈配合恢复并适配的 144 C ABI / grpc 兼容层；输入版本及归档 SHA256
见 [native/cronet.lock.json](native/cronet.lock.json)。

## 构建原生库

macOS 需要 Python 3.12+、Git、Apple Command Line Tools 或 Xcode；Linux
双架构使用 Docker。所有源码、工具、缓存和产物留在本项目目录。

```sh
python3 scripts/build_cronet.py all --cpu arm64 --jobs 8
./scripts/build_linux.sh
```

默认代理 `127.0.0.1:8897`。输出 `dist/mac-arm64/`、`dist/linux-x64/`、
`dist/linux-arm64/`；每个目录包含库、头文件、版本、许可证及 SHA256 清单。
依赖选择、Docker 交叉编译、旧补丁迁移及验证细节见 [native/README.md](native/README.md)。
原始 [1.patch](1.patch) 保留，不直接套用到新版本。

## 使用

```go
import cronet "github.com/wmm1996528/cronet-go"

params := cronet.NewEngineParams()
params.SetEnableHTTP2(true)
params.SetEnableQuic(true)
if err := params.SetProxyServer("http://127.0.0.1:8897"); err != nil {
    panic(err)
}
// 可选：params.SetProxyCredentials(username, password)
// 可选：params.SetIgnoreCertificateErrors(true)，默认正常验证证书。
if err := params.SetHTTP2Settings(map[uint16]uint32{6: 300000}, true); err != nil {
    panic(err)
}
if err := params.SetTLSCipherSuites([]string{
    "TLS_AES_128_GCM_SHA256",
    "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
}); err != nil {
    panic(err)
}
if err := params.SetTLSCurves([]string{"X25519", "P-256"}); err != nil {
    panic(err)
}
transport := cronet.NewCronetTransport(params, true)
defer transport.Close()
// client := &http.Client{Transport: transport}
```

`NewCronetTransport` 接管并释放 params。HTTP/HTTPS 代理 URL 可含经过 URL 编码的
账号密码；认证头只发送给代理，User-Agent 保持原值。SOCKS4/5 不支持账号认证。
HTTP/2 随机 SETTINGS 使用 Chromium 原生 GREASE，由第二个参数显式开启。
TLS 名称数组也可直接写入 `SetExperimentalOptions` 的 `tls_cipher_suites`、`tls_curves`
顶层字段。空数组保留 Chromium 默认配置；不支持 CookieStore 实验开关。

构建 Go 项目时设置对应目标目录，库与头文件必须配套：

```sh
export CGO_ENABLED=1
export CGO_CFLAGS="-I$PWD/dist/mac-arm64/include"
export CGO_LDFLAGS="-L$PWD/dist/mac-arm64 -lcronet -Wl,-rpath,$PWD/dist/mac-arm64"
go build .
```

Linux 将目录换为 `dist/linux-x64` 或 `dist/linux-arm64`。不需要安装到系统目录。
历史 `examples/` 中的库未覆盖；示例含固定外部目标与代理配置，请先调整。

## 测试

在 GoLand MCP 集成终端执行：

```sh
./scripts/test_cronet.sh mac-arm64
```

运行本地 HTTP/TLS/代理测试与 Go race 检查，日志位于 `.build/logs/`。
