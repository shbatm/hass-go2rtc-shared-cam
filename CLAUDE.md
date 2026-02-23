# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contributing / Git Workflow

**Do NOT push directly to `main`.** All changes must use a feature branch and PR:

```bash
git checkout -b <feature-branch>
# make changes, commit
git push origin <feature-branch>
gh pr create --base main
```

After a PR is merged, mirror to Gitea: `git push gitea main:github-main`

## Project Overview

This is a HACS-compatible Home Assistant custom component (`custom_components/sharedcam`) that manages a standalone go2rtc container for sharing camera streams with authenticated external viewers.

All component code lives under `custom_components/sharedcam/`.

## Architecture

### Component Structure

The component uses a **DataUpdateCoordinator** polling pattern:
- Coordinator polls `GET /api/streams` every 30s for drift correction
- Entities write state **immediately** on switch toggle (do not wait for poll cycle) — `coordinator.async_set_updated_data()` right after the API call succeeds

**Entities created per configured camera:**
- `switch.sharedcam_<name>` — on: `PUT /api/streams`; off: `DELETE /api/streams` + `POST /api/restart`
- `sensor.sharedcam_<name>_viewers` — active viewer count from `consumers` array length
- `binary_sensor.sharedcam_<name>_enabled` — stream key present in `/api/streams` response

**Custom HTTP views registered via `HomeAssistantView`:**
- `GET /api/sharedcam/status/{camera_name}` — JSON snapshot: `available`, `viewers` (or null), `status` (rendered template)
- `GET /api/sharedcam/status/{camera_name}/events` — SSE stream pushed on stream enable/disable, viewer count delta, or template output change

### Infrastructure

**go2rtc-shared API** (the target instance — separate from HA's built-in go2rtc on port 11984):
- Standalone go2rtc container, typically proxied behind a reverse proxy
- No API auth assumed (restrict via IP allowlist at the proxy layer)
- go2rtc version: 1.9.x (tested against 1.9.14)

**go2rtc API endpoints:**
```
PUT    /api/streams?name=<name>&src=<rtsp_url>
DELETE /api/streams?src=<stream_name>    # NOTE: ?src= takes the stream NAME (not RTSP URL)
POST   /api/restart                       # kicks active WebSocket consumers
GET    /api/streams                       # key present = enabled; consumers[] length = viewers
```

**GET /api/streams response — important quirks:**
- `"consumers": null` when no viewers (key is present but null, not absent) — use `or []` guard
- `"consumers": [...]` when viewers are connected

**Frigate RTSP:** `rtsp://<frigate-host>:8554/<stream_name>` (deterministic from config)

**Options (stored in `entry.options`, configured via the integration's Configure button):**
- `show_viewers` (default: `True`) — when `False`, the `viewers` key is omitted from the `/status` and SSE payload entirely; the HA sensor entity still shows the real count
- `status_template` (optional) — Jinja2 template string rendered to `"status"` in the payload. Tracked in the SSE handler with `async_track_template_result`, which auto-discovers all entities the template references and fires on output change.

**Status payload schema:**
```json
// Stream on:  {"available": true, ["viewers": <int>,] ["status": "<rendered string>"]}
// Stream off: {"available": false, "message": "Stream not available at this time"}
```

### go2rtc-client v0.4.0 API — actual surface

`_StreamClient` only exposes `add()` and `list()`. Several operations require the internal `_BaseClient`:

| Operation | Method |
|---|---|
| `streams.add(name, src)` | `PUT /api/streams` ✅ library |
| `streams.list()` | `GET /api/streams` (typed — `dict[str, Stream]`) ✅ library |
| Delete a stream | `client._client.request("DELETE", "/api/streams", params={"src": camera_name})` |
| Restart go2rtc | `client._client.request("POST", "/api/restart")` |
| Get raw streams JSON (with consumers) | `client._client.request("GET", "/api/streams")` then `.json()` |

The `Stream` typed model only has `producers`; **`consumers` is not in the model**. `_async_update_data` uses a raw request to get the full dict including `consumers[]`.

### Key Implementation Rules

- `DELETE` stream must always be followed by `POST /api/restart` (DELETE removes the stream definition but doesn't kick active WebSocket consumers)
- On HA startup, re-register streams that were enabled before restart — go2rtc has no persistent stream config; all state is lost on go2rtc restart. Track enabled state via `entry.options["stream_enabled"]`.
- SSE coordinator listener pushes on viewer count delta **or** stream enabled→disabled transition (covers the 0-viewer case where count doesn't change but `data` goes `None`)
- SSE template tracking uses `async_track_template_result` with `TrackTemplate` — fires when the rendered string changes; auto-discovers all referenced entities; no reload required when template changes (read live from `entry.options`)
- View registration guard: `hass.data[DOMAIN]["_views_registered"]` prevents duplicate HTTP view registration across multiple config entries

### Config Flow Fields (per config entry)

**Step 1 — `async_step_user`:**
- **go2rtc-shared API URL** (default: `http://localhost:1984`)
- **Frigate base RTSP URL** — auto-populated as `rtsp://{host}:8554` derived from the Frigate config entry's HTTP API URL (`entry.data["url"]`) when Frigate is loaded; editable if port differs. Falls back to `rtsp://localhost:8554`.
- **Camera name** — rendered as a `SelectSelector` dropdown populated from `hass.data["frigate"][entry_id]["config"]["go2rtc"]["streams"]` when Frigate is loaded; already-configured cameras are filtered out. Falls back to free-text input if Frigate is not loaded or has no go2rtc streams. Used as the config entry unique ID.
- **Friendly name** (optional) — used as the HA device name

On success, validated config is stored in `self._validated_config` and the flow proceeds immediately to `async_step_options` (grocy pattern — no separate Configure click needed).

**Step 2 — `async_step_options`** (inline during initial setup, also available post-setup via Configure):

`manifest.json` declares `after_dependencies: ["frigate"]` so sharedcam always sets up after Frigate when both are present, ensuring `hass.data["frigate"]` is populated before the config flow renders.

### Options Flow Fields (per config entry, via Configure button or inline during setup)

Implemented as `SharedCamOptionsFlow(config_entries.OptionsFlow)` — **not** `OptionsFlowWithReload` because both options are read live from `entry.options` on every request; no reload is needed.

- **`show_viewers`** (bool, default `True`) — when `False`, `viewers` key is omitted from the payload entirely
- **`status_template`** (str, optional) — Jinja2 template. Example:

```jinja2
{% set temperature = states('sensor.my_temperature', with_unit=True, rounded=True) %}
{% set humidity = states('sensor.my_humidity', with_unit=True, rounded=True) %}
🌡️ {{ temperature }} | 💧 {{ humidity }}
```

Schema uses `_OPTIONS_SCHEMA` + `self.add_suggested_values_to_schema(...)` to pre-fill existing values (HA standard pattern).

### Integration Quality Scale

**Bronze IQS status** (as implemented):
- ✅ `config-flow`, `appropriate-polling`, `dependency-transparency`, `entity-unique-id`
- ✅ `entity-event-setup` (CoordinatorEntity handles lifecycle)
- ✅ `test-before-configure` (`_validate_go2rtc_url` in config flow)
- ✅ `test-before-setup` (`async_config_entry_first_refresh`)
- ✅ `unique-config-entry` (`async_set_unique_id(camera_name)` + `_abort_if_unique_id_configured`)
- ✅ `runtime-data` (`entry.runtime_data = coordinator`; typed alias `SharedCamConfigEntry: TypeAlias = ConfigEntry[SharedCamCoordinator]`)
- ✅ `has-entity-name` (`_attr_has_entity_name = True` + `DeviceInfo` on all entities)
- ✅ `docs-high-level-description`, `docs-installation-instructions`, `docs-removal-instructions` — covered by README.md (`docs-actions` N/A — no service actions)
- ⏳ `config-flow-test-coverage` — deferred (no tests yet)

**Reference**: [Integration Quality Scale](https://developers.home-assistant.io/docs/integration_quality_scale_index) — full rule list in the HA developer docs.

### HACS Requirements

- `hacs.json` present
- `manifest.json` with `version`, `requirements: ["go2rtc-client==0.4.0"]`, `iot_class: "local_polling"`, `after_dependencies: ["frigate"]`

### External Viewer Integration

The viewer page consumes the SSE endpoint. The reverse proxy (e.g. Caddy) must proxy `/status*` to HA with `flush_interval -1` (disables buffering so SSE events are delivered immediately):

```caddyfile
route /status* {
    reverse_proxy https://<ha-host> {
        header_up Authorization "Bearer {env.HA_TOKEN}"
        flush_interval -1
    }
}
```
