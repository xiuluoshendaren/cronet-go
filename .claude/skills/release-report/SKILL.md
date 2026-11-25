---
name: release-report
description: 对比当前工作区与目标 tag/branch 的差异，生成结构化上线报告（功能明细、SQL 改动、上线顺序、各应用发布判断、Dockerfile 改动），并在用户明确确认上线后打递增版本 tag 并 push。当用户提到"上线、发布、出上线报告、release、deploy、对比 tag 差异、打版本/tag、准备发版"时必须使用本 skill，即使用户没有明确说"报告"二字。
---

# 上线报告与发版

## 概述

流程分两个阶段，中间有硬性确认门：

1. **报告阶段**：对比当前工作区 ↔ 目标 tag/branch，产出上线报告到项目 `.claude/release/`，按项目文档交付规则暂存、commit 并 push 报告所在分支
2. **发版阶段**：用户审阅并明确说"确认上线"后，才打新版本 tag 并 push tag

未经用户明确确认，绝不执行**版本 tag 或 tag push**；报告的普通 commit / 分支 push 不等于确认上线，也不能因此省略。默认全部用中文写报告。

## 步骤 1：确定对比基线

- 目标 ref 由用户指定（tag 或 branch）。用户没给时，默认取最新版本 tag：
  ```bash
  git fetch --tags --quiet
  git tag --list 'v*' | sort -V | tail -1
  ```
- 无版本 tag 时，要求用户提供明确的对比 ref，不自行选择无关基线。
- 记录当前分支、HEAD commit、工作区是否干净：
  ```bash
  git rev-parse --abbrev-ref HEAD
  git log -1 --format='%h %s'
  git status --porcelain
  ```
- 有未提交/未推送改动时，在报告开头显著标注，并提醒用户：tag 只打在最终 HEAD commit 上，未提交内容不会进入本次发版。把未提交改动也列入报告供用户判断；报告自身须按项目规则先提交并推送分支，确认打 tag 前重新核对 HEAD。

## 步骤 2：收集差异

```bash
# 提交清单
git log <base>..HEAD --no-merges --date=short --pretty=format:'%h %ad %s'
# 文件级差异
git diff <base>...HEAD --stat
git diff <base>...HEAD --name-status
# 未提交改动（若有）
git diff --stat
git diff --cached --stat
git diff --cached
git status --porcelain
```

当 commit message 信息不足以说明改动时（如只有 "fix"、"wip"），读对应 diff 或用 codegraph 弄清实际做了什么，不能照抄含糊信息。

## 步骤 3：归类功能（新增 / 修复 / 优化）

按 commit type 和实际改动内容分三类，逐条件列出，同模块的碎提交合并归纳：

- **新增功能 (feat)**：用户可感知的新能力。写清"谁、在什么场景、能做什么"，不要只重复 commit 标题
- **问题修复 (fix)**：修了什么 bug、触发条件、影响范围
- **优化/重构 (perf/refactor/style/docs/chore)**：性能、体验、结构、依赖等改进

每条标注来源 commit（短 hash）。让不看代码的人读完也能知道本次发版变化。

## 步骤 4：SQL 改动检查

本项目无数据库 migration 目录，报告“二、SQL 改动”固定写“无”。若后续新增数据库内容，先复核实际目录和执行方式再更新本技能。

## 步骤 5：应用发布范围判定

本项目是 Go 模块与 Cronet 原生库，不存在已核实的服务部署单元，不适用单应用整体部署假设。逐项判断：

| 发布对象 | 已核实产物或入口 | 判断依据 |
| --- | --- | --- |
| Go 模块 | go.mod、根目录 *.go；由下游 import | Go 代码/API/依赖变化需判断模块发布；仅项目文档不要求发布运行产物 |
| Cronet 原生库 | 1.patch、examples/cronet/include/、Linux x86-64 so、macOS arm64 dylib | 补丁或 C API 变化需匹配头文件与原生库；不能凭修改补丁认定二进制已重建 |

需确认：目标 Chromium revision、GN 参数、原生构建脚本、目标平台矩阵、产物分发渠道及下游部署入口。仓库未提供完整构建/发布流水线，不得臆造服务、镜像或强制联动。示例不是已确认的生产部署单元。

修改 1.patch 后，应先验证在指定 Chromium revision 应用及编译，核对导出符号与配套头文件，再验证 Go 编译和必要请求行为；原生库与绑定发布顺序须依据实际兼容性说明。仅文档改动可将两项标为“否”，其余按差异逐项给证据，证据不足写“需确认”。

## 步骤 6：Dockerfile / 构建依赖检查

```bash
git diff <base>...HEAD --name-status -- 'go.mod' 'go.sum' '1.patch' 'examples/build.sh' 'examples/cronet/**' 'examples/libcronet.dylib' '**/Dockerfile*' '**/docker-compose*' '.github/**'
```

- 有改动：列出文件 + 改了什么（基础镜像、系统依赖、语言依赖、构建步骤），提示是否需要重新构建镜像、镜像 tag 是否变化
- 无改动：明确写"无"

## 步骤 7：写报告

报告存项目内 `.claude/release/`（目录不存在则创建）。文件名：`NN-YYYY-MM-DD-release-<新版本tag>.md`。

写文件前先创建 `.claude/release/`，调用可用的「获取目录版本号」skill 取该目录当前最大编号并递增；若技能不可用，按 `^\d{2}-` 扫描本目录取最大编号，不覆盖历史文件。

严格使用下面模板：

```markdown
# 上线报告 YYYY-MM-DD

- 对比基线：<base tag/branch>（<base short hash>）
- 当前分支：<branch>
- 发布 commit：<报告提交前 HEAD；报告随分支提交后的最终 HEAD 需在 tag 前复核>
- 拟定版本：<新版本tag>
- 工作区状态：干净 / 有未提交改动（已在文末注明）

## 一、本次上线内容

### 新增功能
- <功能说明（场景 + 能力）> [<hash>]

### 问题修复
- <bug 说明 + 影响> [<hash>]

### 优化改进
- <优化说明> [<hash>]

## 二、SQL 改动
无 / 或：

| 顺序 | 文件 | 用途 | 备注（幂等/回滚） |
|---|---|---|---|
| 1 | <migration 文件路径> | ... | ... |

执行方式：<项目约定的 SQL 执行方式；执行环境与顺序说明>

## 三、上线顺序
<如：1. 先执行 SQL；2. 部署 X；3. 部署 Y。仅需要其中一个时写清"仅发布该应用"；无顺序要求则写"无严格顺序"，不得把独立部署的应用当成一个发布组>

## 四、应用发布范围

| 应用 | 是否发布 | 依据 |
|---|---|---|
| Go 模块 | 是/否/需确认 | 根目录 Go 代码与 go.mod/go.sum 差异及下游影响 |
| Cronet 原生库 | 是/否/需确认 | 补丁、C API、库文件差异及实际重建证据 |

## 五、Dockerfile / 构建依赖
无 / 或：<文件 + 改动内容 + 镜像重建提示>

## 六、发版操作
确认上线后执行：
  git tag -a <新版本tag> <HEAD> -m "release <新版本tag>"
  git push origin <新版本tag>
```

报告写完后按项目规则，从仅包含本次文件的目录执行 `git add .`，提交并 push 报告所在分支；不要顺带提交其他会话的文件。更新报告中关于工作区/HEAD 的描述（避免"尚未提交"与事实冲突），确认远端分支已同步。**这一步不是发版确认，不打 tag、不推 tag。** 然后向用户口述要点（三类内容摘要、SQL、各应用的逐项判定与证据），明确询问是否确认上线。

## 步骤 8：确认后打 tag 并 push

只有用户明确确认（如"确认上线""打 tag 吧"）才执行。确认前核对要打 tag 的目标分支（当前若是功能分支，不暗自改到 main）、报告 commit 已在该分支 HEAD、发布范围与用户确认一致；证据不足的"需确认"项先补证再操作。

```bash
# 重新 fetch，防止别人刚打过同名 tag
git fetch --tags --quiet
# 计算下一版本：最新版本 tag 末位 +1
git tag --list 'v*' | sort -V | tail -1
```

版本规则：沿用现有 vMAJOR.MINOR.PATCH 风格；本地已核实最大 tag 为 v1.11.0。默认下一版本末位 +1（如 v1.11.1），用户指定版本优先；每次发版前重新 fetch 并核对远端，不把本地缓存当最新版本。用 `-a` 打带注释 tag：

```bash
git tag -a <新版本tag> -m "release <新版本tag>"
git push origin <新版本tag>
```

- push 被拒绝（远端已有同名 tag）→ 停下报告，重新计算版本号，不要强推
- 打错 tag 且未 push：`git tag -d <tag>` 删除重来；已 push 的不得擅自删除远端 tag，交用户处理
- 完成后回报：新 tag、指向 commit、报告路径

## 边界

- 只生成报告、打 tag、push tag。不直接部署服务器、不执行生产 SQL（SQL 执行须走项目约定通道且需用户确认）
- 报告属项目文档；报告阶段依项目规则 `git add .`、commit、push 报告分支，确认上线后才打/推版本 tag。各应用独立部署时，报告不能自动触发任何应用发布。
