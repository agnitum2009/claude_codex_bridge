# CCB Mobile Cloudflare Tunnel Alpha Setup

Status: alpha / developer preview

This guide describes the current Cloudflare Tunnel route for CCB Mobile. The
mobile gateway stays bound to loopback. Cloudflare owns the public HTTPS/WSS
route, while CCB owns pairing, device tokens, terminal tokens, ProjectView
redaction, and local device revocation.

## Prerequisites

- A CCB project that can start normally with `ccb`.
- `cloudflared` installed on the server.
- A Cloudflare account with a domain already using Cloudflare nameservers.
- A hostname you control, for example `mobile.example.com`.
- WebSockets enabled for the zone in Cloudflare Network settings.

Quick Tunnels are useful for development smoke tests, but Cloudflare documents
them as testing/development only. Use a named tunnel for a stable alpha setup.

## Create The Named Tunnel

Run these commands on the server that hosts CCB:

```bash
cloudflared tunnel login
cloudflared tunnel create ccb-mobile
cloudflared tunnel route dns ccb-mobile mobile.example.com
```

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <tunnel-uuid>
credentials-file: /home/<user>/.cloudflared/<tunnel-uuid>.json

ingress:
  - hostname: mobile.example.com
    service: http://127.0.0.1:8787
  - service: http_status:404
```

Check the tunnel:

```bash
cloudflared tunnel info ccb-mobile
```

## Start CCB Mobile Gateway

In the CCB project directory, start the gateway:

```bash
ccb mobile serve \
  --listen 127.0.0.1:8787 \
  --public-url https://mobile.example.com \
  --route-provider cloudflare_tunnel
```

This command prints a short-lived pairing code and a claim endpoint. It does
not bind a public listener. The public URL is pairing metadata only.

In another terminal, start the Cloudflare tunnel:

```bash
cloudflared tunnel run ccb-mobile
```

## Pair The Mobile App

Use the printed gateway URL and pairing code in the mobile app's gateway
pairing screen. The pairing code expires after 10 minutes by default and can be
claimed once.

The paired device receives these default scopes:

- `view`
- `focus`
- `terminal_input`

Terminal-open tokens are short-lived and expire after 5 minutes by default.
Terminal input and paste frames must use monotonic sequence numbers, and
reconnect requires the latest output resume cursor after a disconnect.

## Manage Paired Devices

Run these commands from the same CCB project directory on the server. They are
local management commands and are not exposed through the public tunnel.

List paired devices:

```bash
ccb mobile devices
```

Revoke a lost or retired device:

```bash
ccb mobile revoke <device_id>
```

Revocation marks the device as revoked and also revokes still-open terminal
handles for that device. Future terminal token authentication fails if the
owning device has been revoked.

## Development Smoke Validation

If you are working from the `ccb_mobile` development checkout, validate a named
tunnel with:

```bash
tools/mobile_gateway_terminal_smoke.py \
  --gateway-listen 127.0.0.1:8787 \
  --gateway-public-url https://mobile.example.com \
  --route-provider cloudflare_tunnel
```

The smoke is accepted only when route diagnostics are ready, ProjectView and
terminal-open responses remain redacted, terminal input/paste/resize/close and
resume reconnect pass, and cleanup stops the disposable CCB runtime.

## Safety Notes

- Do not use `--listen 0.0.0.0:...`; the gateway intentionally rejects
  non-loopback listen addresses.
- Do not treat Cloudflare Access identity as a replacement for CCB device
  identity. Cloudflare Access can be optional defense-in-depth later, but CCB
  pairing and device tokens remain authoritative.
- Do not expose tmux socket paths, tmux session names, or raw pane authority in
  public route payloads.
- Do not use Quick Tunnels as the normal alpha route.

## Related Cloudflare Documentation

- Quick Tunnels:
  <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/>
- Locally-managed tunnels:
  <https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/create-local-tunnel/>
- Tunnel routing:
  <https://developers.cloudflare.com/tunnel/routing/>
- WebSockets:
  <https://developers.cloudflare.com/network/websockets/>
