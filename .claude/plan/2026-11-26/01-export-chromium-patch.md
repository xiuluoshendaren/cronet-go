# 导出 Chromium 159 源码补丁

## 目标

将本次升级对 Chromium 源码的修改导出为根目录 `2.patch`，包括恢复的 native/grpc_support、新增 TLS/代理实现、macOS CLT 和嵌套 BoringSSL 修改。排除构建产物、缓存和本机杂项。

## 工作包

| 编号 | 内容 | 状态 |
| --- | --- | --- |
| WP1 | 核对源码修改及新增文件范围 | 已完成 |
| WP2 | 导出统一路径补丁，验证锁定源码可应用 | 已完成 |
| WP3 | 记录使用说明，暂存审查并本地提交 | 已完成 |

## 结果与验证

- 根目录 `2.patch` 包含 91 个文件，646079 字节。
- 基于 Chromium `4deb883708d3d25100c5aac2148aafc95dae95ac`，BoringSSL `7968531b8f882e3ab4c38fac8d8674231f40442e`。
- 包含 144 native/grpc_support 恢复文件、桌面构建、macOS CLT、代理/证书/HTTP2/TLS 定制。
- 以 macOS 源码树导出；与 Linux 的功能源码一致，Cronet BUILD.gn 仅格式差异。
- 不含 DEPS 下载裁剪、Linux 无关文件删除、.DS_Store、工具链、产物及 Go 绑定。
- 独立临时 Git 仓库按固定 revision 恢复原始文件；正向检查、实际应用、91 个文件逐字节对比、反向检查均通过，并保留原始可执行权限。
- 补丁头部包含基线和应用命令；在已同步依赖的干净 Chromium src 根目录运行 `git apply --check /path/to/2.patch` 后再执行 `git apply /path/to/2.patch`。
- 本次只导出源码补丁，未改运行代码，无需重复三平台编译和单元测试。
- 暂存检查：patch 空白上下文行需要保留单个空格，因此使用 `git -c core.whitespace=-blank-at-eol diff --cached --check`，检查通过。
