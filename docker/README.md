# Docker Infrastructure Setup

Sample Docker Compose stack: a go2rtc container and Caddy sidecar that together serve the viewer page and stream endpoint.

```
HA (SharedCam) ──► go2rtc  ──┐
                              ├── internal-net
Frigate (RTSP) ──► go2rtc  ──┘
                              Caddy ──── external-net ──── Reverse proxy (auth) ──── Viewer
                              (status proxy, optional)
                              └── HA
```

---

## Directory Structure

```
docker/
├── docker-compose.yml       # go2rtc + Caddy services
├── .env.example             # Environment variable template — copy to .env
├── caddy/
│   └── Caddyfile            # Path routing: stream WS, optional status proxy, static files
├── config/
│   └── go2rtc.yaml          # go2rtc config — no static streams (component manages them)
└── www/
    └── index.html           # Viewer frontend
```

---

## Setup

### 1. Environment

```bash
cp .env.example .env
```

`HA_TOKEN` is **optional** — only needed if using the [status template feature](../README.md#options), which proxies `/status*` from Caddy to HA. If you're not using it, leave it empty and remove the `/status*` block from the Caddyfile.

If you do need it, create a long-lived access token at **HA → Settings → Profile → Security → Long-Lived Access Tokens**.

### 2. Configure the Caddyfile

If using the status endpoint, edit `caddy/Caddyfile` and replace `<ha-host>:<ha-port>` with your HA instance's **direct** LAN address and port (e.g. `192.168.1.10:8123`). Otherwise remove the `/status*` block entirely.

> **Point Caddy directly at HA, not at a reverse proxy in front of it.** Routing through Nginx Proxy Manager or similar causes connection hangs on the status endpoint (HTTP/2 multiplexing keeps the connection open). Use the plain HTTP LAN address even if HA is normally served over HTTPS externally.

Also add Caddy's Docker network subnet to HA's `trusted_proxies` in `configuration.yaml`:
```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.25.0.0/16   # adjust to match your Docker network subnet
```

### 3. Networks and reverse proxy

The compose file uses two external Docker networks:

| Network | Who's on it | Purpose |
|---|---|---|
| `internal-net` | go2rtc, Caddy | Internal network, either only for this stack or it can be common to other local services (e.g. an internal-only reverse proxy). go2rtc must be reachable by HA (stream management) and by Caddy (stream serving). Never exposed externally. |
| `external-net` | Caddy, your reverse proxy | Your authenticated reverse proxy routes inbound viewer traffic to Caddy. go2rtc is **not** on this network. |

Rename the networks to match your existing setup. If you're not using Docker networks for one or both, uncomment the relevent `ports:` entries in the compose file and point your proxy directly to the host ports.

> **go2rtc must not be reachable externally.** If using an untrusted internal network, restrict port 1984 to HA's IP at the host's firewall or an internal reverse proxy layer.

### 4. Start

```bash
docker compose up -d
```

---

## What Each Part Does

### go2rtc (`config/go2rtc.yaml`)

No static streams — SharedCam registers and removes them at runtime via the REST API. No RTSP or WebRTC listeners; streams are served exclusively via the WebSocket API. Restarting the container clears all streams; HA re-registers enabled ones on startup.

### Caddy sidecar (`caddy/Caddyfile`)

Path-based filter in front of go2rtc (and optionally HA):

- **`/api/ws*`, `/video-rtc.js`, `/video-stream.js`** → go2rtc. The management API is never proxied.
- **`/status*`** → HA (optional). Bearer token injected server-side; the browser never sees HA credentials.
- **Everything else** → static files from `/www`.

> `flush_interval -1` is required on the HA proxy block — without it Caddy buffers the response, breaking SSE.

### Viewer page (`www/index.html`)

Single-page viewer that connects to the go2rtc WebSocket stream, shows an overlay when the stream is unavailable, polls every 30s to detect when it comes back, and optionally shows a status bar driven by the SSE endpoint.

---

## Attribution

`www/index.html` is derived from [go2rtc `stream.html`](https://github.com/AlexxIT/go2rtc/blob/master/www/stream.html) by Alexey Khit, used under the [MIT License](https://github.com/AlexxIT/go2rtc/blob/master/LICENSE). It uses go2rtc's `video-stream.js` web component and WebSocket API; the overlay, reconnect logic, and SSE status bar are original additions.
