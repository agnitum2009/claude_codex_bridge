<div align="center">

# CCB 手机 App 来了！

**基于去中心化多 Agent 设计**
**可见、可控的多 Agent 交互 TUI 工作台**

<p>
  <img src="https://img.shields.io/badge/version-8.0.8-orange.svg" alt="version">
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20WSL-lightgrey.svg" alt="platform">
  <img src="https://img.shields.io/badge/providers-15%20CLI%20families-0B7285.svg" alt="providers">
</p>

<p>
  <img src="https://img.shields.io/badge/Codex-111111?style=flat-square&logo=openai&logoColor=white" alt="Codex">
  <img src="https://img.shields.io/badge/Claude-D97757?style=flat-square&logo=anthropic&logoColor=white" alt="Claude">
  <img src="https://img.shields.io/badge/Gemini-4285F4?style=flat-square&logo=googlegemini&logoColor=white" alt="Gemini">
  <img src="https://img.shields.io/badge/Kimi-111111?style=flat-square&logo=moonshotai&logoColor=white" alt="Kimi">
  <img src="https://img.shields.io/badge/MiMo-FF6900?style=flat-square&logo=xiaomi&logoColor=white" alt="MiMo">
  <img src="https://img.shields.io/badge/Qwen-6A5CFF?style=flat-square" alt="Qwen">
  <img src="https://img.shields.io/badge/Cursor-111111?style=flat-square" alt="Cursor">
  <img src="https://img.shields.io/badge/Copilot-111111?style=flat-square&logo=githubcopilot&logoColor=white" alt="GitHub Copilot">
  <img src="https://img.shields.io/badge/Crush-FF5A5F?style=flat-square" alt="Crush">
  <img src="https://img.shields.io/badge/Kiro-6D5EF6?style=flat-square" alt="Kiro">
  <img src="https://img.shields.io/badge/Pi-111111?style=flat-square" alt="Pi">
  <img src="https://img.shields.io/badge/Z.ai-111111?style=flat-square" alt="Z.ai">
  <img src="https://img.shields.io/badge/OpenCode-111111?style=flat-square" alt="OpenCode">
  <img src="https://img.shields.io/badge/Antigravity-6D5EF6?style=flat-square&logo=google&logoColor=white" alt="Antigravity">
  <img src="https://img.shields.io/badge/Droid-3DDC84?style=flat-square&logo=android&logoColor=white" alt="Droid">
</p>

**中文** | [English](README.md)

[快速开始](#快速开始) · [Mobile App](#mobile-app) · [Rich 模式](#rich-mode-new) · [配置团队](#创建项目配置) · [使用文档](docs/manuals/user-guide/) · [开发文档](docs/manuals/developer-guide/)

<p align="center">
  <img src="assets/readme_v7/ccb-hero-zh-light.png" alt="CCB v7 可见多 Agent CLI 工作台" width="960">
</p>

</div>

## 为什么用 CCB？

* 强稳定的 agent 间通信能力，支持 `A -> B -> C`、`A,B -> C`、`A -> B,C` 等复杂协作关系。
* 每个 agent 都是完整原生终端，支持可见的界面排布和直接接管。
* 后台 daemon 持续运行，可以脱离前台界面保持项目状态。
* Hub 能力：一个命令同时并发运行多家 CLI provider。
* 手机远程控制器：跨 provider 语音操控、文件传输和远程终端访问。

**全新角色规范**：可把 skills、记忆和工具依赖封装进自封闭 Role Pack，快速生成可热加载、可卸载的专业 agent。

## 快速开始

### 1. 基本功能和操作

#### 1.1 安装

```bash
npm install -g @seemseam/ccb
```
<details>
<summary><b>GitHub release 包和源码安装兜底</b></summary>

如果当前环境不方便使用 npm，可以到 [Releases](https://github.com/SeemSeam/claude_codex_bridge/releases) 下载与你的平台匹配的包，解压后安装：

```bash
tar -xzf ccb-*.tar.gz
cd ccb-*
./install.sh install
```

源码安装只建议开发或临时兜底使用：

```bash
git clone https://github.com/SeemSeam/claude_codex_bridge.git
cd claude_codex_bridge
./install.sh install
```

源码安装会让全局 `ccb` / `ask` 链接回当前 checkout。普通用户更建议使用 npm 包。

</details>

#### 1.2 启动

在工作目录执行：

```bash
ccb
```
如果启动时提示无法自动创建 `.ccb` 或找不到项目锚点，需要手动创建 `.ccb` 作为项目锚点：

```bash
mkdir -p .ccb
```

<a id="mobile-app"></a>

#### 1.3 手机远程控制（Android）

推荐使用手机控制 CCB：可以接入所有 CCB 项目，控制每个 agent，语音输入，并传递文件。

```bash
ccb update mobile
```

该命令会指导您完成安装和配置。

<p align="center">
  <img src="assets/readme_v7/mobile-control-chat.jpg" alt="CCB Mobile agent 对话" width="180">
  <img src="assets/readme_v7/mobile-control-terminal.jpg" alt="CCB Mobile 终端控制" width="180">
  <img src="assets/readme_v7/mobile-control-files.jpg" alt="CCB Mobile 文件传输" width="180">
  <img src="assets/readme_v7/mobile-control-pairing.jpg" alt="CCB Mobile 配对和连接" width="180">
</p>

<p align="center">
  <sub>手机端可切换项目和 agent、查看对话、打开终端、传递文件，并通过配对流程安全接入。</sub>
</p>

<details>
<summary><b>Mobile App 详情、安全边界和源码</b></summary>

CCB 8.0.8 已把 Flutter 版 CCB Mobile 源码放入 [`mobile/`](mobile/)，
并在 GitHub Release 中发布 Android APK：

- [下载 CCB Mobile v8.0.8 APK](https://github.com/bfly123/claude_code_bridge/releases/download/v8.0.8/ccb-mobile-v8.0.8.apk)
- App 源码：[`mobile/app`](mobile/app)
- 服务端 gateway 源码：[`lib/mobile_gateway`](lib/mobile_gateway)

手机端定位是远程控制真实服务器上的 CCB 项目。它可以从 server-wide
mobile gateway 获取所有已挂载项目，切换 window/agent，渲染 agent
对话上下文，以 pane-native 输入方式发送文本，打开 terminal 视图，并通过
认证 gateway 上传/下载图片和文档附件。

首次配置建议：

```bash
ccb update mobile
```

然后按终端提示：

1. 在桌面/服务器和手机上安装并登录同一个 Tailscale tailnet。
2. 启动 CCB 打印的 loopback-only Mobile gateway 和 Tailscale Serve 命令。
3. 在 Android 手机上安装 APK。
4. 打开 CCB Mobile，扫描配对二维码。

安全边界：

- CCB gateway 只绑定 loopback，例如 `127.0.0.1:8787`。
- 远程访问使用 Tailscale Serve，不启用 Tailscale Funnel。
- CCB 不保存 Tailscale 密码、OAuth token、admin API token，也不会自动修改
  tailnet ACL/grants。
- 手机只获得 pairing profile 授权的 scope，例如 view、content、terminal、
  file upload 和 file download。

</details>

<a id="rich-mode-new"></a>

#### 1.4 Rich 富媒体终端

在终端查看文件结构、打开文件、编辑文档和预览媒体内容。

<p align="center">
  <img src="assets/readme_v7/rich-workbench.png" alt="CCB rich 富媒体工作台在 WezTerm 中使用 Yazi 预览" width="860">
</p>

```bash
ccb update rich
```

rich 启用后，普通 `ccb` 会自动打开 rich WezTerm launcher，只有当当前已经处于 CCB 自己拉起的 rich WezTerm 中时才不会再次跳转；运行 `ccb uninstall rich` 可退回普通终端启动。

<details>
<summary><b>Rich 模式详情</b></summary>

运行 `ccb update rich` 安装可选富媒体工作台；它会尽量封装 Yazi 等二进制，并用 WezTerm 承载富媒体终端界面，提供 Markdown 渲染和图片/PDF/视频预览。安装后，普通 `ccb` 会自动打开 rich launcher，只有当当前已经处于 CCB 自己拉起的 rich WezTerm 中时才不会再次跳转；`ccb rich` 仍可作为显式启动入口。

</details>

#### 1.5 更新
安装完成后，后续更新直接使用 CCB 自带 updater：

```bash
ccb update
```

<a id="创建项目配置"></a>

### 2. 创建项目配置

在项目根目录创建 `.ccb/ccb.config`。推荐使用 v2 `[windows]` 拓扑：
window 内的 agent 排布由 `,` 和 `;` 控制上下堆叠和左右分栏，例如 `A,B;C,D` 接近四宫格布局。

```toml
version = 2

[windows]
main = "main:codex"
work = "worker1:codex(worktree), worker2:claude(worktree)"
review = "reviewer:claude, qa:gemini"

[ui.sidebar]
mode = "every_window"
width = "15%"
bottom_height = 20
agents_height = "50%"
comms_height = "15%"
tips_height = "35%"
comms_limit = 3
```

如果你不确定应该如何分组、要几个 worker、哪些 agent 用 worktree、哪些 agent 需要独立模型或 API，可以直接问当前工作台里的 `ccb_self`。它是 CCB 内置的 self-agent，理解 CCB 命令、配置权威层、roles、windows、reload 边界和常见恢复路径，并能用私有 `ccb-config` skill 和你讨论后生成配置方案。空白项目默认包含 `ccb_self`。

验证配置：

```bash
ccb config validate
```

启动工作台：

```bash
ccb
```

### 3. 开始协作

你可以直接在某个 agent pane 里输入，也可以让 agent 之间协作：

```text
/ask reviewer review the latest parser changes and list blocking issues.
```

也可以在工作编排中让 agent 自动调用 `/ask` 完成委派和交接。建议通过修改 agent 记忆或项目共享记忆 `.ccb/ccb_memory.md` 进行编排。

**后续超强编排正在开发中**

### 4. Agent Roles Spec 规范和角色库

CCB 支持 [Agent Roles Spec](https://github.com/SeemSeam/agent-roles-spec)：这是一个 host-neutral 的专业 agent 封装规范，可把专业角色打包成可安装、可挂载、可卸载的 Role Pack。该仓库同时也是公开角色库。

<details>
<summary><b>当前角色库</b></summary>

| Role | 基本功能 |
| :--- | :--- |
| `agentroles.ccb_self` | CCB 自维护、配置辅助、运行诊断、受保护恢复和工作流编排。 |
| `agentroles.archi` | 架构审查、边界检查、耦合分析、可维护性风险和后续 gate 建议。 |
| `agentroles.frontend_engineer` | 前端设计与实现、设计系统、可访问性、浏览器 QA 和受审查的 AGY 委派。 |
| `agentroles.mobile_app_engineer` | iOS、Android、React Native、Expo、Flutter、SwiftUI、Jetpack Compose 等移动端设计与实现。 |
| `agentroles.mother` | Role 创建、Role source 审计、角色研究、蓝图设计和 Agent Roles 规范合规检查。 |
| `agentroles.su_ccb` | SU-CCB 工作流操作，覆盖需求分析、计划、派发、审查 gate、归档和恢复。 |

</details>

### 5. 联系方式

- Email: `bfly123@126.com`
- **[Telegram group & contact / TG 群与联系](https://t.me/+BKn03v8I_ehmYzRk)**
- 微信: `seemseam-com`

<p align="center">
  <img src="assets/weixin.jpg" alt="微信群" width="240">
</p>

---

### 6. 社区和致谢

感谢 [Linux.do 社区](https://linux.do) 在测试、反馈和讨论中的支持。

感谢 [tmux-agent-sidebar](https://github.com/hiroppy/tmux-agent-sidebar) 提供的 sidebar 思路和启发。

<details>
<summary><b>版本记录</b></summary>

### 7. 新版本记录

v7 线重点：

- 原生 CCB sidebar，支持 per-window 项目视图、agent 状态和鼠标切换。
- Comms 从 agent 活动中拆分，通信状态和 provider pane 活动更清晰。
- 新增 `version = 2` `[windows]` 拓扑，可按工作流分组多个 tmux window。
- 显式 `ccb reload` 支持动态加载 agent/window 和 idle 卸载，不重启无关 agent。
- 保留 compact / hybrid 旧配置兼容，单窗口团队不需要强制迁移。
- 加固 tmux、Ghostty、release helper、Codex trust 和 provider 会话恢复路径。

<details open>
<summary><b>v8.0.0</b> - CCB Mobile Monorepo 发布</summary>

- Flutter 版 CCB Mobile 源码正式进入本仓库，并在 GitHub Release 中发布
  Android APK。
- 新增 server-wide mobile 项目发现、配对、认证 gateway 路由、pane-native
  消息输入、对话上下文渲染、terminal 访问，以及图片/文档上传下载能力。
- 将 `ccb update mobile` 提升为 Tailscale Tailnet onboarding 的统一入口，
  同时保持 gateway 仅监听 loopback，不启用 Funnel、不保存 token、不自动修改
  ACL/grants。

</details>

<details>
<summary><b>v7.7.0</b> - Runtime Accelerator 发布加固</summary>

- Release artifacts 现在会携带可选 Rust `ccb-runtime-accelerator`，安装版
  Codex agent 在预期存在 sidecar 时不再静默退回 Python 热路径。
- 当项目路径导致 Unix socket 路径过长时，accelerator socket 会自动落到
  短的 per-user runtime socket root。
- 加固 callback repair 和 Codex binding cache invalidation，并记录完整
  回归、长 idle Codex soak、Claude callback 和混合 provider 集成测试证据。

</details>

<details>
<summary><b>v7.6.19</b> - 长任务 ask 默认等待策略</summary>

- 普通长时间 `ask` 默认继续等待真实 provider/completion 结果，不再仅因
  heartbeat 诊断自动 terminalize 为 `incomplete/heartbeat_timeout`。
- Codex、Claude、Gemini 的 pane-backed no-terminal timeout 默认改为显式
  opt-in，仍保留显式 reliability timeout 策略。
- 已用 32 分钟 source-runtime ask smoke 验证：任务超过 30 分钟仍保持
  running，随后以 `result_message` 完成，未出现 `heartbeat_timeout` 或
  `incomplete` 证据。

</details>

<details>
<summary><b>v7.6.18</b> - CCB UI 主题偏好</summary>

- 新增顶层 `ccb theme` 主题切换命令，可调整 CCB 自有 tmux/sidebar UI，
  并支持用 `+` / `-` 在深色和浅色 palette 间循环。
- 新增适合浅色 terminal 背景的 tmux status、pane border、sidebar、agent
  活动状态和 comms 状态配色。
- 生成的 rich WezTerm profile 会读取同一个全局 CCB 主题偏好，并在下次
  打开或 reload 时同步主题。

</details>

<details>
<summary><b>v7.6.17</b> - Codex Log Symlink Target 修复</summary>

- 当 `/tmp/ccb-codex-logs-*` 清理导致 managed Codex `logs_2.sqlite` 临时
  symlink target 目录消失时，启动前会自动重建 target parent。
- 如果坏 symlink 无法修复，CCB 会先移除 symlink 并恢复本地备份，再让
  Codex 初始化自己的 SQLite 数据库。
- 增加缺失 symlink target parent 启动路径的回归测试。

</details>

<details>
<summary><b>v7.6.16</b> - Codex SQLite Migration 恢复修复</summary>

- 修复 managed Codex `logs_2.sqlite` redirect：CCB 不再预创建 Codex 自有
  SQLite schema，改为等待 Codex 自己完成 migration。
- 只有在 Codex 创建 log database 和 `_sqlx_migrations` 记录后，才安装 CCB
  的 diagnostic insert-block trigger。
- 对中间问题版本留下的异常临时 log database 做自愈：先挪到备份，再让
  Codex 通过正常 migration 路径重新创建。

</details>

<details>
<summary><b>v7.6.15</b> - Codex 诊断与 Sidebar Focus 修复</summary>

- managed Codex 默认把 `logs_2.sqlite` 诊断写入重定向到临时存储，并阻断
  diagnostic log insert；diagnostics 模式可恢复原始数据库路径用于排查。
- 如果临时 SQLite symlink 无法安装，会回退到 in-place diagnostic trigger
  路径，避免启动失败。
- 修复 sidebar 点击其他 tmux window 中 agent 的聚焦路径：先选择目标
  window，再选择 pane；缺少 window 元数据时继续保留 pane id 兜底。

</details>

<details>
<summary><b>v7.6.14</b> - Mobile Gateway Alpha 与 Codex 诊断治理</summary>

- 新增 Mobile Gateway Alpha 能力：认证 pairing、focus routes、terminal
  open/resume/history routes、websocket terminal frames、public route metadata
  和设备撤销命令。
- 新增 sidebar 右侧放置能力，并把 canonical `[ui.sidebar]` 渲染扁平化；
  legacy `[ui.sidebar.view]` 输入继续兼容。
- 支持多个本地 agent 共用同一个 Role Pack role id，不再被折叠成单一运行时身份。
- 降低 Codex diagnostic SQLite 写盘抖动：默认过滤 TRACE/DEBUG 日志行并保留
  INFO/ERROR；设置 `CCB_CODEX_DIAGNOSTIC_LOGS=1` 可关闭过滤。

</details>

<details>
<summary><b>v7.6.13</b> - Provider Profile Overlay 修复</summary>

- Codex plugin override 现在按预期顺序解析：继承的 source config、
  `provider_profile.plugins`，最后是
  `CCB_CODEX_PLUGIN_OVERRIDES_JSON` / `CCB_CODEX_PLUGIN_OVERRIDES` 环境覆盖。
- 没有继承 `config.toml` 的 Codex agent 现在也会把
  `provider_profile.plugins` 写入 managed `config.toml`。
- Claude `provider_profile.mcp_servers` 现在即使 source `.claude.json`
  不存在也会生效，`enabled = false` 会清理 agent trust file 里的 stale
  managed MCP server。
- callback continuation 现在会保留明确的 upstream finalization target；
  继承的 ask skills 也会提醒 agent 在 upstream 结果可用前不要提前回答
  callback continuation。

</details>

<details>
<summary><b>v7.6.12</b> - Claude MCP 与 Hook 继承</summary>

- managed Claude agent 现在会从 source `.claude.json` 继承 Claude Code MCP
  配置，包括全局 `mcpServers` 和当前 project/workspace 的 MCP server 状态。
- project 级 MCP 状态只映射到当前 managed workspace key，不会把无关 source
  project 记录复制进 agent home。
- source-home Claude Code hooks 会与 CCB-managed finish/activity hooks 合并，
  用户安装的 hook 工具在 agent restart 后仍可见。
- managed Claude `.claude.json` 现在按 secret provider state 处理，因为 MCP
  定义可能包含环境变量或接近认证材料的启动配置。

</details>

<details>
<summary><b>v7.6.11</b> - Layout Percent 与 Codex MCP Overlay</summary>

- 新增显式 pane split 比例 layout token，例如 `agent1:codex@30`；没有
  `@N` 后缀时继续保持原有 sibling panes 均分行为。
- 新增通过 `provider_profile.mcp_servers` 配置 per-agent Codex MCP overlay；
  同名 MCP server 覆盖继承配置，不同名 additive。
- managed Codex home projection 现在会保留可信 Codex command hook，并改进
  sidebar Comms/Tips 的滚动和拖拽调整，同时在 `ccb trace` 暴露更多 reply
  artifact 证据。

</details>

<details>
<summary><b>v7.6.10</b> - Z.ai Provider 支持</summary>

- 新增 Z.ai CLI optional provider：支持 `provider = "zai"`、可见
  `zai --directory` pane，以及 per-job `zai --prompt` 执行。
- 使用 Z.ai 原生 subprocess 完成边界：进程退出加 JSONL stdout 中的
  assistant 内容提取，不要求模型打印 `CCB_DONE`。
- 新增 `ZAI_START_CMD`、provider session/pathing、deterministic stub、
  focused execution 测试，并同步 README provider 支持列表。

</details>

<details>
<summary><b>v7.6.9</b> - Kimi / AGY Provider 可靠性</summary>

- Kimi execution 现在记录 receipt、无捕获输出诊断、trace 和 resume
  metadata，便于定位缺失回复和恢复 turn。
- AGY prompt delivery 现在等待 ready evidence，处理 pane fallback 和
  ambiguous tmux send 结果，并更清楚地报告合并请求诊断。
- dispatcher、mailbox trace 和 text artifact 诊断现在会暴露排查 Kimi/AGY
  delivery 与 completion 边界所需的 provider 细节。

</details>

<details>
<summary><b>v7.6.8</b> - Role Pack Current Store</summary>

- Role Pack 运行时现在跟随 `.roles/installed/<role-id>/current` 下的当前安装包；
  旧的多版本 store 只作为兼容输入，不再是运行时主权。
- 项目 `.ccb/role-lock.json` 现在是 legacy diagnostic：CCB 不再写入、不再从
  lock adopt，也不会因为旧 lock 残留而 suppress role memory/skills。
- provider 启动 session 会记录 role id、version 和 digest；当启动 digest 与
  installed current 不一致时，restart 会明确失败，而不是静默恢复旧 provider
  会话并假装采用了新 role。
- release artifact 元数据 patch 现在指向 bash launcher 拆分后的 `ccb.py`，
  确保构建出的 tarball 携带正确版本。

</details>

<details>
<summary><b>v7.6.7</b> - Rich Workbench 闭环</summary>

- 普通 `ccb` 和 `ccb rich` 现在会启动 CCB 托管的 rich WezTerm；只有已经在该
  CCB 托管 rich 会话内时才跳过自动启动，普通外部 WezTerm 不再误判为 rich。
- 运行入口统一走 `_ccb-python` launcher，让安装版和源码版命令都固定到预期
  Python 解释器。
- 内置默认配置继续把 `ccb_self` 放在独立 `claude` window，同时普通默认启动
  不恢复 standalone Neovim tool window。

</details>

<details>
<summary><b>v7.6.6</b> - Role Store Home Pinning</summary>

- role store lookup 现在会固定在 managed provider home 之外，provider session
  改写 `HOME` 时不再误查 provider-local `.roles` 目录。
- CCB 启动边界会保留 `AGENT_ROLES_STORE`；未显式设置时回退到真实
  source/account home 下的 role store。
- 缺失 role 的诊断会打印解析后的 role store 路径，便于定位 provider-home
  漂移问题。

</details>

<details>
<summary><b>v7.6.5</b> - Rich WezTerm 输入法</summary>

- 生成的 rich WezTerm 配置现在会启用 IME，并把 `XMODIFIERS=@im=...`
  映射为 WezTerm 的 XIM 名称，修复 X11 下 fcitx/ibus 中文输入连接问题。
- 生成的 `ccb-workbench` wrapper 会在启动 WezTerm 前探测运行中或已安装的
  `fcitx5`、`fcitx`、`ibus-daemon`，只在用户未设置时补齐输入法环境变量。
- 保留 v7.6.4 已绿发布面，以及 v7.6.2 的 rich/tmux 修复，供 npm latest
  安装实测。

</details>

<details>
<summary><b>v7.6.4</b> - macOS Release Install Smoke</summary>

- 保留 7.6.3 的 macOS temporary-root 加固，同时让 CI release install smoke
  对隔离的 sibling `CODEX_BIN_DIR` 显式设置临时 bin override。
- 不放宽用户侧 installer 安全规则，但允许 release workflow 从临时 smoke root
  验证 macOS 包安装。
- 保留 v7.6.2 已发布的 rich workbench 与 tmux 单行 status 修复，供用户安装
  实测。

</details>

<details>
<summary><b>v7.6.3</b> - macOS CI 绿灯补丁</summary>

- install guard 现在会识别 GitHub Actions macOS runner 使用的
  `${TMPDIR:-/tmp}` canonical parent，避免 `/private/var/folders/...` 临时
  路径被误放行。
- doctor 的 temporary implementation 检测同步兼容 macOS `/tmp` symlink
  行为，避免 `/private/tmp` 和 `/private/var/folders/...` 路径导致 CI 误红。
- 保留 v7.6.2 已发布的 rich workbench 与 tmux 单行 status 修复，供用户安装
  实测。

</details>

<details>
<summary><b>v7.6.2</b> - Rich Workbench 热修复</summary>

- `.ccb/ccb.config` 现在可以把 `rich` 当作工具/layout alias 使用，不需要
  provider runtime；它会 materialize 成托管工具 pane/window，不会成为 `ask`
  目标。
- `ccb update rich` 启用 bundle 后，普通 `ccb` 在既有 rich/WezTerm 会话外可
  自动走 rich launcher，同时避免递归重复拉起 WezTerm。
- 新增 `ccb uninstall rich`、`ccb rich uninstall` 和 `ccb rich disable`，
  可回到普通 CCB 启动；完整 `ccb uninstall` 语义保持不变。
- rich 更新只清理 CCB-owned legacy editor roots 和链接，不会碰用户自己的
  editor 安装和个人配置。

</details>

<details>
<summary><b>v7.6.1</b> - Rich Workbench 二进制封装</summary>

- `ccb update rich` 会优先封装并验证 Yazi/ya 二进制，再让包管理器兜底。
- Linux rich 安装优先使用官方 Yazi musl 构建，再回退 GNU 构建，避免旧稳定
  发行版遇到较新的 glibc 要求。
- 下载的 Yazi 二进制必须通过 `--version` 验证才会启用；无效的 managed
  二进制会被移除，保证后续 fallback 仍可工作。
- WSL 下 rich launcher 可使用 Windows 原生 `wezterm.exe`，同时让 CCB、Yazi
  和 preview helpers 继续运行在当前 Linux 发行版内。

</details>

<details>
<summary><b>v7.6.0</b> - Rich Workbench 生命周期</summary>

- Rich workbench 变为显式可选 bundle，统一通过 `ccb update rich` 安装和更新。
- 普通 `install.sh install` 和 `ccb update` 只处理 CCB 本体，不再自动
  provision standalone Neovim。
- 公开 `ccb tools ... neovim` 路由会拒绝 standalone provisioning 并提示
  `ccb update rich`；`ccb rich` 只启动已经安装并启用的 rich bundle。
- CCB tmux 状态栏恢复为单行，移除旧的第二行复制提示。

</details>

<details>
<summary><b>v7.5.3</b> - Kimi 运行可靠性与 Hindsight 兼容性</summary>

- 增强 Kimi 运行路径，但不改变其他 provider 的执行路径：当 native turn
  log 没有及时暴露完成回复时，Kimi 可对 K2.7 Code 使用稳定 pane 证据兜底。
- Kimi Hindsight 记忆改为 CCB 执行边界上的显式 opt-in：只有配置
  `.hindsight/kimi.json`、`.hindsight/codex.json`、`HINDSIGHT_API_URL` 或
  `HINDSIGHT_BANK_ID` 时才启用，失败时只记录 provider diagnostics，不阻塞任务。
- CCB 物化 managed Codex home 时会保留可信 Codex command hook，包括
  Hindsight Codex hooks。运维可通过 `CCB_CODEX_INHERITED_HOOK_EVENTS` 和
  `CCB_CODEX_INHERITED_COMMAND_HOOK_MARKERS` 扩展 allowlist；任意 root hook
  仍会被过滤。
- Kimi bridge 和 `scripts/hindsight` helper 同时兼容 `HINDSIGHT_API_KEY` 与
  `HINDSIGHT_API_TOKEN`。
- README 更明确展示支持的 provider surface，同时保持无关 provider 行为不变。

</details>

<details>
<summary><b>v7.5.2</b> - Native CLI Provider Wave</summary>

- 新增 Qwen Code（`qwen`）、Cursor Agent（`cursor`）、GitHub
  Copilot CLI（`copilot`）、Crush（`crush`）、Kiro CLI（`kiro`）、Pi（`pi`）和 Z.ai CLI（`zai`）
  作为内置 optional provider。
- 使用原生 per-job CLI 执行和 provider 自有完成信号：Qwen、Cursor、
  Copilot 和 Pi 解析 stream-json / JSON result 事件；Crush、Kiro 和 Z.ai CLI 使用进程退出
  加 stdout。新增适配器不要求模型打印 `CCB_DONE`；Pi 以原生 `turn_end`
  作为结束点。
- 新增 `QWEN_START_CMD`、`CURSOR_START_CMD`、`COPILOT_START_CMD`、
  `CRUSH_START_CMD`、`KIRO_START_CMD`、`PI_START_CMD`、`ZAI_START_CMD` 命令覆盖，以及 provider session
  binding、runtime launcher、deterministic stub 和 focused execution 测试。

</details>

<details>
<summary><b>v7.5.1</b> - MiMo Provider 发布面</summary>

- 在 README 公开 provider strip 增加带 Xiaomi 标识的 MiMo 徽标，并把
  首页定位更新为 8 个 CLI family。
- 将已提交的 MiMo native provider 集成纳入 7.5 线发布：managed `mimo`
  pane、`MIMO_START_CMD`、生成式 MiMo instructions，以及
  `mimo run --pure --format json` 完成解析。
- 同步 npm package metadata 和 release workflow 默认 tag 到新的 patch
  release。

</details>

<details>
<summary><b>v7.5.0</b> - 原生 CLI Provider 与首页同步</summary>

- 新增 Kimi managed native CLI provider 支持，并补齐更通用的 native CLI
  runtime 基础能力，覆盖 runtime spec、session binding、启动命令覆盖和清理路径。
- Kimi 和 Antigravity 的完成判定改为读取 provider 自有 session 或
  transcript 证据，不再要求模型打印 `CCB_DONE`。
- CCB auto-permission 对 Kimi 默认注入当前版本支持的 `--auto-approve`，
  同时识别 `--auto`、`--yes`、`-y`、`--yolo` 等旧版或别名标识，避免重复注入。
- 同步英文和中文 README 首页，刷新 hero assets，并统一为 7 个公开 CLI
  family 的定位。

</details>

<details>
<summary><b>v7.4.4</b> - Claude end_turn 与 npm 发布面修复</summary>

- Claude pane-backed ask 在 primary assistant response 带
  `stop_reason=end_turn`、已看到请求 anchor 且回复非空时，会立即产生
  `TURN_BOUNDARY(reason=assistant_end_turn)` 并正常完成，不再等到 900 秒
  reliability timeout。
- 空的 session-boundary terminal event 如果之前没有 assistant 回复证据，会
  终止为 `incomplete/task_complete_empty_reply`，并带
  `empty_provider_reply` 诊断。
- 恢复 `@seemseam/ccb` npm 发布面：补回 package metadata、CLI runner
  wrappers，以及等待 GitHub release assets 后再发布 npm 包的 Trusted
  Publishing workflow。
- 刷新 v7 README 首页：使用 canonical hero assets，默认 npm-first 安装，并
  更明确说明 `ccb_self` 是 CCB 内置的使用、配置、诊断和恢复专家。

</details>

<details>
<summary><b>v7.4.3</b> - PR #225 可靠性跟进修复</summary>

- 恢复 Claude launcher contract：inline `--settings` 只反映 materialized
  settings overlay，不再把 provider env 注入 settings JSON。
- 修复 Claude 在 WSL 调 Windows executable 时的环境透传：路径变量使用 `/p`
  转换，`ANTHROPIC_*` API 值作为 raw env 名透传。
- 加固 Antigravity resume lookup，兼容 SQLite 返回的 `bytes`、`str` 和
  `memoryview` metadata，并在查找失败时降级为 `--continue`。
- 新增 Claude settings contract、WSL API env forwarding 和 AGY resume
  fallback 的回归测试。

</details>

<details>
<summary><b>v7.4.2</b> - Self-supervision 与空回复防护</summary>

- 通过有界 provider-runtime snapshot、project-view 活动证据、suspicion
  envelope 和 self-first diagnosis path 加固 CCB self-supervision。
- Claude/Gemini hook 空回复、Codex protocol `task_complete` 空回复，以及
  AGY done-marker 空回复会终止为带 diagnostics 的 `incomplete`。
- 保留有意的无回复语义：`--silence` 成功仍是 `completed`，callback parent
  的 `callback_pending` 空回复仍合法，异常 silent completion 仍可诊断。
- 收紧默认 Role Pack install 和项目 role-lock refresh，覆盖
  `agentroles.archi` 与 `agentroles.ccb_self`。

</details>

<details>
<summary><b>v7.4.1</b> - Maintenance heartbeat 与 ccb_self 默认配置</summary>

- 加固项目级 maintenance heartbeat runner、schedule 处理、activation
  去重抑制和 diagnostics 证据路径，同时保持 heartbeat 只能显式启用。
- 空白项目内置默认配置新增 `ccb_self:codex` 并绑定 canonical
  `agentroles.ccb_self`，安装/更新时刷新推荐角色，但不改写已有自定义配置。
- CCB source 与 `agent-roles-spec` 的角色 id `agentroles.ccb_self` 对齐；
  `agentrole.ccb_self` 仅作为 legacy 输入兼容。
- 收紧生成配置的单一权威、Role Pack hook 的 CCB_BIN/project-root 路径和
  Codex prompt delivery acceptance guard。
- 新增 `ccb_self` expert manual、plan decisions，以及 expert reference 和
  communication recovery guidance 相关测试。

</details>

<details>
<summary><b>v7.4.0</b> - ccb_self 自维护角色</summary>

- 新增 `agentroles.ccb_self` 自维护 Role Pack 路径，覆盖 CCB 配置所有权、运行诊断、受保护恢复、工作链修复和单 agent 重启辅助。
- 完整 `ccb-config` 改为 `ccb_self` 私有内置 skill，不再作为全局继承 skill 发给所有 agent。
- 安装/更新的 Role Pack provisioning 默认安装或刷新推荐默认角色，包括 `agentroles.ccb_self`。
- 空白项目内置默认配置新增 `ccb_self:codex`，并绑定 `agentroles.ccb_self`；已有自定义配置仍可显式添加 `agentroles.ccb_self:codex`。

</details>

<details>
<summary><b>v7.3.8</b> - AGY adapter 与项目 tmux history</summary>

- 新增 Antigravity (`agy`) `pane_quiet` execution adapter，包含协议解析、命令分发、轮询和配套文档，可作为 CCB 托管 provider 运行。
- CCB 托管项目 tmux session 默认保留 50000 行 scrollback history，并覆盖 project namespace 创建/复用和 detached runtime fallback 路径。
- 在 authoritative project session 存在后，稳定重放 tmux mouse、vi key、clipboard、focus 和 history 策略。
- Claude startup 会尽量以内联 JSON 传递 `--settings`，避免非 ASCII source path 在 provider 启动链路中失效。

</details>

<details>
<summary><b>v7.3.7</b> - Ask 参数策略与 skill 指引</summary>

- inherited Claude、Codex、Droid ask skills 改为先按结果意图选择参数：`--silence`、`--compact`、`--artifact-reply` 或普通 `ask`。
- 依赖关系保持显式：只有 active 父任务必须等待子任务结果时才追加 `--callback`。
- artifact transport 与任务关系分离：需要精确输入或输入/输出保真时才使用 `--artifact-request` 和 `--artifact-io`。
- README / README_zh 的 Agent Collaboration 小节新增 ask 参数速查表。
- 新增 ask-parameter-policy plan tree、决策记录、参数矩阵和验证记录。

</details>

<details>
<summary><b>v7.3.6</b> - Provider memory ownership 清理</summary>

- 新增 provider memory ownership policy：Claude、Codex、OpenCode 的托管上下文不再把 provider-native project memory 重复注入 CCB 生成 bundle；Gemini 暂时保留旧行为，等待单独审计。
- 只在 provider user memory 源层过滤旧 CCB install marker blocks 和 legacy collaboration sections，不改写用户自己的 memory 文件。
- 默认 `.ccb/ccb_memory.md` template 升级到 v5，移除已由 CCB managed memory 提供的重复 Ask Communication 块。
- 新增 seed-aware shared memory migration：只升级未编辑过的旧生成模板，保留用户编辑过的项目记忆。
- Claude route-mode install 不再写 `~/.claude/rules/ccb-config.md`；install/uninstall 只删除带 CCB marker 的旧 external config，保留未标记用户文件。
- 修复 source runtime startup 的 tmux UI version detection import cycle，保持 `ccb_test` 路径可安全启动。

</details>

<details>
<summary><b>v7.3.5</b> - Tmux border hook 热修复</summary>

- 修复 tmux `after-select-pane` hook 可能持久保存 `/tmp/ccb-v...-release.../config/ccb-border.sh` 这类临时 release 路径，导致点击 pane 后报 `returned 127` 的问题。
- border hook 改为 `run-shell -b` 并带可执行 guard，脚本路径失效时不会反复刷 tmux 错误。
- `ccb update` 后 best-effort 刷新当前 tmux UI hooks，让从 v7.3.4 升级的 session 自动重写坏 hook，且不会把 UI 刷新失败算作 Role Pack provisioning failure。
- v7.3.4 已撤回并标记为 prerelease；稳定升级目标请使用 v7.3.5 或更新版本。

</details>

<details>
<summary><b>v7.3.4</b> - Withdrawn Prerelease</summary>

- `agentroles.archi` tooling 简化为统一使用全局 `@seemseam/archi` npm 包；CCB 不再拆分管理 Hippo、llmgateway、pip、venv、git 或 editable Archi 依赖。
- `ccb roles install/update/doctor agentroles.archi` 对齐 npm 提供的 `archi` CLI 以及包内 bundled Hippo/llmgateway capabilities。
- `bin/ccb-arch` 改为转发到 `archi`；缺失时直接提示 `npm install -g @seemseam/archi`。
- 修复 sidebar focus/refresh 行为，从 sidebar 选择 agent 不再不必要地 restart panes。
- 已撤回：tmux border hook 可能持久保存临时 release 路径并在之后报 `ccb-border.sh ... returned 127`；请使用 v7.3.5 或更新版本。
- 新增带保护的 `ccb_test` source entrypoint，用于隔离验证源码 checkout，不影响已安装的 CCB。
- 托管 OpenCode pane 通过 `opencode.json` 和 `OPENCODE_DISABLE_AUTOUPDATE=true` 禁用 autoupdate。
- 刷新继承的 `ccb-config` skills：支持 config-only、跟随用户语言、修复 YAML description quoting、菜单分组更清晰，并将 sidebar refresh 指引改为 restart panes。
- 新增 config-designer UI plan tree，并包含 main 分支的 `@percent` layout split token 与 Antigravity lifecycle cleanup 更新。

</details>

<details>
<summary><b>v7.3.3</b> - Withdrawn Draft</summary>

- 该版本因 sidebar focus/refresh regression 在稳定 rollout 前撤回，不作为推荐 release，也不应用于升级；请使用 v7.3.5 或更新版本。

</details>

<details>
<summary><b>v7.3.2</b> - 首次安装 Role Pack provisioning 修复</summary>

- 修复完全空白环境首次安装时的 Role Pack provisioning 问题：`install.sh` 在 `agentroles.archi` 尚未安装时先执行 update，可能导致 provisioning 未完成。
- 保留已有安装的刷新路径：仍先执行 `ccb roles update agentroles.archi`，当返回 role not installed / run roles install / run agent-roles install 时 fallback 到 `ccb roles install agentroles.archi`。
- 将可选 Role Pack provisioning 的 skip 提示从 update 对齐为 install。
- v7.3.1 仍是已发布版本，但存在空白环境首次安装 Role Pack provisioning bug；新安装和稳定推荐版本请使用 v7.3.2。

</details>

<details>
<summary><b>v7.3.1</b> - Agent Roles、Artifact Ask 和共享 Workspace Release</summary>

- 新增 daemon 管理的 ask artifact 传输：`--artifact-request`、`--artifact-reply` 和 `--artifact-io`，长输出可通过 callback 继续传递 artifact 路径。
- Agent Roles store 路径稳定到外部 `agent-roles` manager 和 `.roles/installed`，同时保留 `ccb.archi` 到 `agentroles.archi` 的兼容输入。
- 新增 `workspace_path`、`workspace_group` 共享 workspace 控制，以及 `provider_command_template`，可包裹 CCB 构造好的 provider 启动命令且不破坏 resume。
- 修复 root 下 Claude 启动、OpenCode 恢复旧会话后 `ccb clear` submit 时序、managed Neovim 原始 runtime 路径保留。
- 刷新继承的 `ask` 和 `ccb-config` skills，覆盖 submit-only ask 规则、artifact 模式、windows-first 配置、共享 workspace 和 provider command template。
- 稳定 WSL/root 发布测试，让非 root Claude 命令断言不再受 runner UID 影响。

</details>

<details>
<summary><b>v7.3.0</b> - Superseded Prerelease</summary>

- 已由 v7.3.1 supersede；远端 WSL Tests workflow 暴露了 root-sensitive Claude 命令断言。v7.3.0 GitHub release 保留为 prerelease，未上传正式 release artifacts。

</details>

<details>
<summary><b>v7.2.12</b> - Agent Roles Store Migration Release</summary>

- 默认使用外部 `agent-roles` package manager 执行 Role Pack install、update 和 sync。
- Role Pack payload 默认写入 spec-owned `.roles/installed` store。
- 自动将已有 legacy installed role snapshot 复制到 `.roles/installed`，不删除旧 store；迁移后 runtime lookup 只读取 spec-owned store。
- `ccb roles update --path ...` 也会通过 Agent Roles manager，path update 不再写 legacy CCB store。
- Supersede v7.2.11；v7.2.11 是未完成的 opt-in preview 发布，不应作为推荐版本使用。

</details>

<details>
<summary><b>v7.2.11</b> - Superseded Agent Roles Opt-In Preview</summary>

- 已被 v7.2.12 supersede，因为发布方向从 opt-in `CCB_AGENT_ROLES_MANAGER=1` preview 改为 default-on Agent Roles manager migration。

</details>

<details>
<summary><b>v7.2.10</b> - Role Pack Post-Update Hotfix</summary>

- 修复 managed `ccb update`：可选 Role Pack 和 Neovim provisioning 现在会交给新安装的 `ccb __post-update` entrypoint 执行，不再由旧 updater 进程继续跑。
- 将 legacy installed `ccb.archi` metadata 修复到 canonical `agentroles.archi`，旧 `source_path` 已不存在时会回退到当前 catalog source。
- 可选 post-update provisioning 失败仍只作为 warning；但设置 `CCB_INSTALL_ROLES=1`、`CCB_INSTALL_NEOVIM=1` 或 `CCB_POST_UPDATE_REQUIRED=1` 时，required provisioning 失败会让父 update 失败。
- 新配置说明统一使用 `agentroles.archi`；`ccb.archi` 仅保留为 legacy input alias。

</details>

<details>
<summary><b>v7.2.9</b> - Agent Roles Catalog Release</summary>

- 将生产架构角色从 CCB 源码树移出，改为从 `agent-roles-spec` 消费 `agentroles.archi`。
- 增加 catalog 驱动的 role list/install/update/sync/add/doctor 流程，并覆盖 installed-role metadata、project lock、digest pinning 和显式 re-add 更新。
- 将 role memory、CCB adapter memory、provider skills 和 Architec adapter hooks 投影到 managed provider home。
- 保留 `ccb.archi` 兼容输入别名，但写入 canonical `agentroles.archi` binding 和 lock。
- 修复 source runtime guard：从源码 checkout cwd 发起的 `ccb --project <allowed-test-dir> ...` smoke 命令现在会按目标项目校验，可通过发布 gate。
- 将生成的 soak、fastpath 和 storage cleanup smoke 目录显式传入 `CCB_SOURCE_ALLOWED_ROOTS`。
- 将 WSL mounted startup smoke 在 `/mnt/c/Temp` 下生成的项目显式传入 `CCB_SOURCE_ALLOWED_ROOTS`。
- 加固 Claude restart provider blackbox 测试：等待 running partial reply 反映出来后再断言。
- 加固 Role Pack CI fixture，使完整 GitHub Actions 测试不再依赖 sibling `agent-roles-spec` checkout。

</details>

<details>
<summary><b>v7.2.8</b> - Superseded Role Fixture Hotfix</summary>

- v7.2.8 已由 v7.2.9 取代；发布 gate 发现完整 GitHub Actions runner 没有 Role Pack 测试预期的 sibling `agent-roles-spec` checkout。

</details>

<details>
<summary><b>v7.2.7</b> - Superseded WSL Mounted Smoke Hotfix</summary>

- v7.2.7 已由 v7.2.8 取代；发布 gate 发现 Claude restart partial-reply 断言存在 provider blackbox timing race。

</details>

<details>
<summary><b>v7.2.6</b> - Superseded Official Smoke Root Hotfix</summary>

- v7.2.6 已由 v7.2.7 取代；发布 gate 发现 main Tests workflow 里的 WSL mounted startup smoke 也需要把 `/mnt/c/Temp` 下生成的项目传入 `CCB_SOURCE_ALLOWED_ROOTS`。

</details>

<details>
<summary><b>v7.2.5</b> - Superseded Source Runtime Guard Hotfix</summary>

- v7.2.5 已由 v7.2.6 取代；发布 gate 发现官方 soak、fastpath 和 storage cleanup smoke 需要把生成的测试根显式传入 `CCB_SOURCE_ALLOWED_ROOTS`。

</details>

<details>
<summary><b>v7.2.4</b> - Superseded Agent Roles Catalog Release</summary>

- v7.2.4 已由 v7.2.5 取代；发布 gate 发现源码 checkout cwd 发起的 `--project` 命令会在 CCBD real platform smoke 中被 source runtime guard 拒绝。

</details>

<details>
<summary><b>v7.2.3</b> - Root Install Support Validation Hotfix</summary>

- 保留 v7.2.2 的 root 安装确认行为：root 安装必须显式确认，卸载仍不受该门控影响。
- 保留安装 identity metadata 和 `ccb doctor` runtime user / owner / root 诊断。
- 修复 WSL 发布验证：安装 metadata 测试在需要时显式模拟非 root 身份，避免被 runner 实际 root 身份影响。

</details>

<details>
<summary><b>v7.2.2</b> - Root Install Confirmation Release</summary>

- 新增明确的 root 安装确认门：`install.sh install` 默认拒绝 root 执行，交互输入 `yes` 才允许，非交互 root 安装必须设置 `CCB_ALLOW_ROOT_INSTALL=1`。
- root 确认门只作用于安装，不阻止卸载清理，因此 root-owned 安装仍可移除。
- 安装 metadata 现在记录 root 状态、install user 和 sudo user 信息。
- `ccb doctor` 增加 runtime user、owner、root 状态诊断，并在 root 运行于非 root 项目时给出 warning。
- 修复架构审查提到的非阻断 build-info 类型卫生项：`read_build_info()` 现在返回 `dict[str, object]`。

</details>

<details>
<summary><b>v7.2.1</b> - Antigravity Runtime Follow-Up</summary>

- 补齐 `agy` / Google Antigravity 的 runtime 和 session 管线：provider runtime spec、client spec、provider-core 公共导出，以及 `.agy-<agent>-session` 命名。
- 增加命名 Antigravity pane 启动回归覆盖，包含 `AGY_START_CMD`、auto-permission、restore continuation 和 prepared-state 兼容。
- 对齐 README provider 列表和发布面，让 Antigravity 与 Codex、Claude、Gemini、OpenCode、Droid 一起出现在用户可见说明中。
- 明确 no-change reload 语义：配置无变化时执行非 dry-run `ccb reload` 返回 `noop` / `no_op`，且不发布 graph。
- 增加 Agent Roles 公开规格项目规划文档，作为未来 host-neutral RolePack 项目的设计记录。

</details>

<details>
<summary><b>v7.2.0</b> - Role Packs And Managed Tools Release</summary>

- 新增 Role Pack 体验面，内置 `ccb.archi` 架构师 role，包含 role memory、Codex/Claude skill 投影和项目 role lock。
- `ccb roles add ccb.archi:codex` 成为主要接入命令；config 保留 shorthand，运行时解析为本地 agent `archi`。
- `ccb roles install/update ccb.archi` 默认刷新 role 资产和依赖；安装/更新时交互提示，非交互场景会给出后续运行命令。
- 新增托管工具 window、sidebar 行和安全的 reload add/remove 行为。
- 包含 main 上已合入的 `agy` / Google Antigravity provider 支持。

</details>

<details>
<summary><b>v7.1.1</b> - Sidebar View Height Release</summary>

- 在 `[ui.sidebar.view]` 下新增三段 sidebar 高度配置：`agents_height`、`comms_height`、`tips_height`。
- 原生 sidebar 默认内部分区调整为 Agents `50%`、Comms `15%`、Tips `35%`。
- config 解析、project_view payload、reload 计划和 Rust sidebar TUI 都会传递并使用这些高度设置。
- 修复同名 agent reload/remount 可靠性：动态卸载后的 retired agent 可以用同名重新创建，不再被旧 runtime authority residue 阻塞；已停止的旧 session 记录仍可保留并供重建继承。
- 同步更新 Codex/Claude 继承的 `ccb-config` skill 文档和 reference，生成或迁移 windows topology 时会暴露这三个参数。

</details>

<details>
<summary><b>v7.1.0</b> - Dynamic Reload Release</summary>

- 新增 `.ccb/ccb.config` 显式热加载：`ccb reload --dry-run` 预览计划，`ccb reload` 应用支持的变更。
- 可以在当前 ccbd daemon 下动态挂载追加的 agent 和新增 window，不打断无关 pane。
- 可以动态卸载 idle 状态下被移除的 agent 和被移除的 idle window，并保留其他 agent pane。
- config signature drift 会被视为 reload-pending，而不是 daemon 重启触发器；busy 卸载和不安全替换仍会 fail closed。

</details>

<details>
<summary><b>v7.0.11</b> - Provider Activity And Sidebar Focus Release</summary>

- 通过 provider-native hook artifact 记录活动证据，让 sidebar 更准确地区分 active、pending、idle 和 failed provider 工作状态。
- project focus 成功后会失效 project view cache，并立即刷新同一 project session 内的 sidebar panes，减少鼠标/聚焦操作后的状态滞后。
- 普通 tmux pane 点击恢复为直接 `select-pane -t = ; send-keys -M`，避免走隐藏子进程路径造成点击响应变慢。
- 同步加固 namespace config、provider hook 安装设置、clipboard/runtime launch 路径和 Codex managed trust 处理，并补充聚焦回归测试。

</details>

<details>
<summary><b>v7.0.10</b> - Sidebar Tips And Tmux Controls Release</summary>

- 保持原生 sidebar 三栏比例稳定：Tree `1/3`、紧凑 Comms `1/4`、Tips `5/12`。
- 扩展默认 Tips：未配置自定义 tips 的项目会显示 pane 移动/resize、window 切换、copy mode、paste、help 等 tmux 快捷键。
- 保留右上角 `↻` 和 `×` 控制：`×` 执行 project-level `ccb kill`，`q` 和 `Esc` 只退出 sidebar。
- 文档和运行态继续保留 CCB-managed tmux Vim 控制：`mode-keys vi`、copy-mode `v` / `C-v` / `y`、`prefix+h/j/k/l`、`prefix+H/J/K/L`。

</details>

<details>
<summary><b>v7.0.9</b> - README v7 Redesign Release</summary>

- 重写 `README_zh.md`，围绕 v7 可见多 agent 工作台、任务优先上手、多 agent 方案对比、v7 界面速览、快速开始、tmux 常规操作、配置示例和安装更新流程组织内容。
- 新增 `assets/readme_v7/` 真实 v7 终端截图，用于 README 演示。
- 保留 README 重设计计划和辅助资料到 `docs/plantree/`。
- 保持 v7.0.8 的 runtime、`ccb clear`、config overlay 和 sidebar 修复不变，只刷新 GitHub 面向用户的文档包。

</details>

</details>

完整历史请看 [CHANGELOG.md](CHANGELOG.md)。
