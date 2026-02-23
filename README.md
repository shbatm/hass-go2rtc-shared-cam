# Home Assistant Shared Cam

A HACS-compatible Home Assistant custom component that manages a **standalone go2rtc instance** for sharing camera streams with authenticated external viewers.

Useful for sharing camera streams securely via a short url (https://sharedcam.example.com/?src=nursery) and making use of your existing SSO solutions or short-term link sharing to a single camera.

Instead of exposing your Frigate instance or HA directly, this component registers selected camera streams in a dedicated go2rtc container, where they are served to external viewers through a reverse proxy with authentication. Streams are disabled by default — sharing a camera is a deliberate, per-camera action from within Home Assistant.

> **Security note**: This component is one layer in a multi-layer security model. See [Security Considerations](docs/SECURITY_CONSIDERATIONS.md) for the full architecture.

![Demo](docs/demo.gif)

---

## How It Works

```
Frigate/RTSP ──► go2rtc-shared ──► Caddy sidecar ──► Reverse proxy (auth) ──► External browser
                        ▲
               HA component (this)
               registers/removes streams
               via go2rtc REST API
```

1. The HA component registers a Frigate RTSP stream in go2rtc when a switch entity is turned on
2. A Caddy sidecar exposes only the go2rtc WebSocket stream endpoint and the viewer page — the go2rtc management API is never reachable externally
3. A reverse proxy (e.g. Nginx, Traefik + Authentik, Pangolin, Cloudflare Access) gates all external access with authentication
4. Authenticated viewers access a simple browser page to receive the stream via go2rtc's MSE/WebSocket transport

---

## Background & Inspiration

This component was directly inspired by [campass](https://github.com/evandcoleman/campass) by [@evandcoleman](https://github.com/evandcoleman), which solves a similar problem — sharing a specific camera with an external viewer via a PIN-protected page, controlled from HA. If campass fits your setup, it is a well-built, self-contained solution worth considering.

The key difference is in **where video flows**, **resource usage**, and **whether your HA URL is exposed**:

**campass** routes video through HA itself using HA's HLS/MJPEG stack:
- HA is in the critical path — if HA is slow, restarting, or busy, the stream is affected
- HLS involves server-side stream re-segmentation and temporary segment storage; there is non-trivial CPU and I/O overhead even for a single viewer
- HLS introduces multi-second buffering by design; latency is noticeably higher than a direct WebSocket stream
- The viewer page is served from your HA instance, which means your HA URL (or nabu.casa URL) must be reachable and is visible to viewers

**This component** keeps HA entirely out of the video path:
- go2rtc pulls directly from Frigate's RTSP source — once the stream is enabled, video flows `Frigate → go2rtc → viewer` with no HA involvement
- go2rtc does no transcoding — it forwards the existing H.264/H.265 stream directly to the browser via MSE/WebSocket. CPU use is minimal even under load
- The entire stack — go2rtc and Caddy sidecar — is two statically-linked Go binaries. With an active stream, measured memory usage is around 20 MB combined (~8 MB go2rtc + ~12 MB Caddy) with under 1% CPU on a single core; at idle it is lower still
- Delivery is via go2rtc's MSE/WebSocket transport, which is sub-second latency
- The viewer page is served from a standalone Caddy sidecar with its own domain — your HA URL is never exposed to external viewers. HA only controls whether the stream is registered; it is otherwise invisible to the viewer

This separation also means the stream stays up even if HA restarts, and the viewer infrastructure can be scaled or replaced independently of HA.

---

## Features

- **Per-camera switch entities** — enable/disable individual streams on demand
- **Viewer count sensor** — active WebSocket consumer count polled from go2rtc every 30s
- **Stream enabled binary sensor** — mirrors go2rtc stream registry state
- **Status HTTP endpoint** — `GET /api/sharedcam/status/{camera_name}` returns a JSON snapshot with stream availability, viewer count, and an optional rendered status string
- **SSE stream** — `GET /api/sharedcam/status/{camera_name}/events` pushes real-time updates to the viewer page when stream state, viewer count, or template output changes
- **Frigate-aware config flow** — when the Frigate integration is loaded, the camera name and RTSP base URL are auto-populated from Frigate's go2rtc stream config
- **Startup recovery** — re-registers enabled streams on HA restart (go2rtc has no persistent stream config)

---

## Prerequisites

- Home Assistant 2024.1+
- A running [go2rtc](https://github.com/AlexxIT/go2rtc) instance (separate from HA's built-in one) — see [Proxy & Docker Setup](#proxy--docker-setup)
- Frigate integration (optional, for auto-populated config flow)
- A reverse proxy with authentication in front of the viewer endpoint — see [Security Considerations](docs/SECURITY_CONSIDERATIONS.md)

---

## Proxy & Docker Setup

A sample stack (go2rtc container + Caddy sidecar + viewer page) is included in the [`docker/`](docker/) directory of this repository.

See **[docker/README.md](docker/README.md)** for setup instructions.

---

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations** → **Custom repositories**
2. Add `https://github.com/shbatm/hass-go2rtc-shared-cam` with category **Integration**
3. Install **SharedCam** from the HACS integration list
4. Restart Home Assistant

### Manual

1. Copy `custom_components/sharedcam/` into your HA `custom_components/` directory
2. Restart Home Assistant

---

## Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **SharedCam**.

| Field | Description |
|---|---|
| **go2rtc API URL** | Base internal URL of your standalone go2rtc instance (e.g. `http://go2rtc-shared:1984` or `https://go2rtc-shared.internal.example.com`) |
| **Frigate base RTSP URL** | RTSP base URL of your Frigate instance (e.g. `rtsp://frigate:8554`). Auto-populated from the Frigate integration when loaded. |
| **Camera name** | go2rtc stream name. When the Frigate integration is loaded this is a dropdown of Frigate's configured go2rtc streams; otherwise free text. |
| **Friendly name** | Optional display name for the HA device. |

One config entry = one camera. Add additional entries for additional cameras.

### Options

After adding a camera, click **Configure** on the integration entry to set per-camera options:

| Option | Default | Description |
|---|---|---|
| **Show viewer count** | On | When off, the `viewers` key is omitted from the `/status` and SSE payload entirely. |
| **Status template** | (none) | Jinja2 template rendered to a plain string and included as `"status"` in the `/status` JSON and SSE payload. May reference any HA entity state or attribute. |

Example status template:

```jinja2
{% set temperature = states('sensor.my_temperature', with_unit=True, rounded=True) %}
{% set humidity = states('sensor.my_humidity', with_unit=True, rounded=True) %}
🌡️ {{ temperature }} | 💧 {{ humidity }}
```

---

## Entities

Per configured camera the component creates one **device** with three entities:

| Entity | Type | Description |
|---|---|---|
| `switch.sharedcam_<name>` | Switch | Turn on to register the stream in go2rtc; turn off to remove it and restart go2rtc to disconnect active viewers |
| `sensor.sharedcam_<name>_viewers` | Sensor | Number of active WebSocket consumers (polled every 30s) |
| `binary_sensor.sharedcam_<name>_enabled` | Binary sensor | `on` when the stream key is present in go2rtc |

State is written immediately on switch toggle — entities do not wait for the 30s poll cycle.

---

## HTTP Endpoints

Both endpoints are registered in HA's HTTP component. They require no separate authentication within HA but should be gated by your reverse proxy when exposed externally.

### `GET /api/sharedcam/status/{camera_name}`

Returns a JSON snapshot. Schema is the same regardless of options — only values change:

```json
// Stream enabled, status template configured
{
  "available": true,
  "viewers": 2,
  "status": "🌡️ 22°C | 💧 65%"
}

// Stream disabled
{
  "available": false,
  "message": "Stream not available at this time"
}
```

- `available` — `true` when the stream is registered in go2rtc, `false` when disabled
- `viewers` — active WebSocket consumer count; omitted when **Show viewer count** is off
- `status` — rendered output of the configured status template; omitted when no template is set

### `GET /api/sharedcam/status/{camera_name}/events`

Server-Sent Events stream. An event is pushed when:
- The stream is enabled or disabled
- The viewer count changes (from the 30s coordinator poll)
- The rendered status template output changes (tracks all entities referenced in the template)

Each event carries the same payload as the snapshot endpoint. The browser can use `EventSource` for zero-lag updates rather than polling.

---

## Security

See [docs/SECURITY_CONSIDERATIONS.md](docs/SECURITY_CONSIDERATIONS.md) for the full security model: layer breakdown, go2rtc API access control, and notes on Frigate RBAC.

---

## Removal

1. Turn off all SharedCam switch entities (this de-registers streams from go2rtc)
2. Go to **Settings → Devices & Services**, find **SharedCam**, and delete each config entry
3. Restart Home Assistant
4. Optionally remove the component files / uninstall via HACS

---

## Roadmap

- [ ] `config-flow-test-coverage` — pytest coverage for the config flow
- [ ] Rework to allow multiple cameras selected in a single integration in HA, currently integration must be added for each camera
- [ ] WebRTC Support
