# Security Considerations

This setup uses a layered security model. The component is one layer — it is not a complete security solution on its own.

The go2rtc instance, Caddy sidecar, and viewer frontend provide no built-in authentication. **You must place an authenticating reverse proxy in front of the viewer endpoint.** Without it, any user who can reach the Caddy container can watch any enabled stream.

---

## Layers

### External access (viewer-facing)

**Reverse proxy authentication** — All external traffic to the viewer domain must be gated by authentication before reaching Caddy. Suitable options: Nginx + OAuth2 Proxy, Traefik + Authentik, Pangolin, Cloudflare Access, or any proxy that enforces authentication before passing requests through.

**Caddy path lockdown** — The Caddyfile exposes only the viewer page, static assets, and the WebSocket stream endpoint (`/api/ws*`). The full go2rtc management API (`/api/streams`, `/api/restart`, etc.) is never reachable externally.

**go2rtc stream registry as access control** — go2rtc has no static streams. Only streams explicitly enabled via the HA switch entity exist in go2rtc. A viewer requesting an unknown `?src=` parameter receives the unavailable overlay — they cannot enumerate or access cameras that have not been explicitly shared.

**Status endpoint** — The `/status*` path (optional) is proxied to HA using a server-side long-lived access token stored in the Caddy container environment. The browser receives only the curated JSON payload and never sees HA credentials or has access to the HA API.

### go2rtc management API

**Restrict to HA's IP only** — The go2rtc REST API (`PUT /api/streams`, `DELETE /api/streams`, `POST /api/restart`) must not be reachable from outside your network or from arbitrary LAN hosts. Restrict it to your HA host's IP at the firewall or reverse proxy layer (e.g. an IP allowlist middleware). The component assumes this restriction is in place and does not add its own authentication to the API calls it makes.

### What the component must not do

- Must not register streams in go2rtc that HA has not explicitly enabled via the switch entity
- Must not expose raw HA state, credentials, or WebSocket access through any endpoint it registers
- Must store the go2rtc URL in HA's config entry store (config flow), not in plain files

---

## A note on Frigate RBAC

Frigate 0.14–0.16 has no per-user camera access control — any authenticated Frigate user can see all cameras. Frigate 0.17 is introducing RBAC, which will allow restricting which cameras a user can access.

**RBAC does not solve the use case this component addresses.** Frigate RBAC controls who can view cameras in the Frigate UI, but it does not provide a mechanism to share a single camera with an externally-authenticated viewer (e.g. a family member or babysitter visiting a link) while keeping the rest of your camera infrastructure private. This component fills that gap by creating an isolated, switch-controlled stream in a separate go2rtc instance with no connection to the rest of your Frigate setup.
