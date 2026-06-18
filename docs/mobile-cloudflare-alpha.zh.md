# CCB Mobile Cloudflare Tunnel Alpha 设置

状态：alpha / 开发者预览

这份文档说明当前 CCB Mobile 的 Cloudflare Tunnel 远程访问路线。Mobile
gateway 仍然只监听 loopback；Cloudflare 只负责公开 HTTPS/WSS 路由；CCB
继续负责配对、设备 token、terminal token、ProjectView 脱敏和本地主机侧设备撤销。

## 前置条件

- CCB 项目可以正常用 `ccb` 启动。
- 服务器已安装 `cloudflared`。
- 有 Cloudflare 账号，并且域名已经使用 Cloudflare nameservers。
- 有一个可用 hostname，例如 `mobile.example.com`。
- Cloudflare Network 设置中启用了 WebSockets。

Quick Tunnels 适合开发 smoke test，但 Cloudflare 官方说明它们只用于测试和开发。
正常 alpha 路线应使用 named tunnel。

## 创建 Named Tunnel

在运行 CCB 的服务器上执行：

```bash
cloudflared tunnel login
cloudflared tunnel create ccb-mobile
cloudflared tunnel route dns ccb-mobile mobile.example.com
```

创建 `~/.cloudflared/config.yml`：

```yaml
tunnel: <tunnel-uuid>
credentials-file: /home/<user>/.cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: mobile.example.com
    service: http://127.0.0.1:8787
  - service: http_status:404
```

检查 tunnel：

```bash
cloudflared tunnel info ccb-mobile
```

## 启动 CCB Mobile Gateway

在 CCB 项目目录中启动 gateway：

```bash
ccb mobile serve \
  --listen 127.0.0.1:8787 \
  --public-url https://mobile.example.com \
  --route-provider cloudflare_tunnel
```

这个命令会输出短期 pairing code 和 claim endpoint。它不会监听公网地址。
`--public-url` 只写入配对元数据。

在另一个终端启动 Cloudflare tunnel：

```bash
cloudflared tunnel run ccb-mobile
```

## 配对手机 App

在 mobile app 的 gateway pairing 页面输入输出的 gateway URL 和 pairing code。
pairing code 默认 10 分钟过期，并且只能 claim 一次。

配对设备默认获得这些 scope：

- `view`
- `focus`
- `terminal_input`

terminal-open token 默认 5 分钟过期。terminal input 和 paste frame 必须使用单调递增
sequence number；断线后 reconnect 必须携带最新 output resume cursor。

## 管理已配对设备

下面命令需要在服务器同一个 CCB 项目目录中执行。它们是本地管理命令，不会通过公网
tunnel 暴露。

列出已配对设备：

```bash
ccb mobile devices
```

撤销丢失或弃用的设备：

```bash
ccb mobile revoke <device_id>
```

撤销设备会把设备标记为 revoked，并级联撤销该设备仍未关闭的 terminal handles。
之后如果旧 terminal token 所属设备已被撤销，terminal token 认证会失败。

## 开发 Smoke 验证

如果你在 `ccb_mobile` 开发仓库中工作，可以用 named tunnel 做验证：

```bash
tools/mobile_gateway_terminal_smoke.py \
  --gateway-listen 127.0.0.1:8787 \
  --gateway-public-url https://mobile.example.com \
  --route-provider cloudflare_tunnel
```

只有当 route diagnostics ready、ProjectView 和 terminal-open 响应保持脱敏、
terminal input/paste/resize/close 与 resume reconnect 都通过，并且 cleanup 停止
disposable CCB runtime 时，smoke 才算通过。

## 安全注意事项

- 不要使用 `--listen 0.0.0.0:...`；gateway 会拒绝非 loopback listen 地址。
- 不要把 Cloudflare Access identity 当成 CCB device identity 的替代品。
  Cloudflare Access 后续可以作为可选 defense-in-depth，但 CCB pairing 和 device
  token 才是控制权威。
- 不要在公开 route payload 中暴露 tmux socket path、tmux session name 或原始 pane
  authority。
- 不要把 Quick Tunnels 当成正常 alpha 路线。

## Cloudflare 官方文档

- Quick Tunnels:
  <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/>
- Locally-managed tunnels:
  <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/create-local-tunnel/>
- Tunnel routing:
  <https://developers.cloudflare.com/tunnel/routing/>
- WebSockets:
  <https://developers.cloudflare.com/network/websockets/>
