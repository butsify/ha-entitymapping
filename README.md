# UI Entity Mapper

A HACS-installable Home Assistant custom integration that lets you create
rule-based mappings between entities entirely through the UI — no YAML
automations required.

---

## Features

- **Full UI management** — add, edit, delete, enable/disable, duplicate mappings from Settings → Devices & Services.
- **Five mapping modes** — boolean mirror, numeric pass-through, numeric scaled, numeric threshold, and light mirror.
- **Bidirectional support** — propagate state changes in both directions with built-in ping-pong loop prevention.
- **Configurable retry** — retry a failed command up to *N* times after a configurable delay.
- **Dashboard entities** — each mapping exposes enabled-switch, last-result sensor, success/failure counters, last-error text, and a run-once button.
- **Services** — reload, enable, disable, run-once, export, and import mappings programmatically.

---

## Installation via HACS

1. Open HACS in your Home Assistant instance.
2. Click **Custom Repositories** (⋮ menu → Custom repositories).
3. Add `https://github.com/butsify/ha-entitymapping` as type **Integration**.
4. Search for **UI Entity Mapper** and click **Download**.
5. Restart Home Assistant.

---

## Initial Setup

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **UI Entity Mapper** and click it.
3. The integration is created immediately — no host or credentials required.
4. Click **Configure** on the integration card to open the mapping manager.

---

## Creating Mappings

Click **Configure** → **Add mapping**:

**Step 1 — Basic settings**

| Field | Description |
|---|---|
| Mapping name | Human-readable label shown on dashboard entities |
| Source entity | The entity whose state changes drive the mapping |
| Target entity | The entity that receives commands |
| Direction | `Unidirectional` or `Bidirectional` |
| Enabled | Toggle the mapping on/off without deleting it |
| Prevent feedback loops | Suppresses echo events after our own writes (recommended `on`) |
| Retry delay (s) | Seconds to wait before retrying if the target did not reach the desired state (`0` = no retry) |
| Max retries | Number of retry attempts (`0` disables retries even if a delay is set) |

**Step 2 — Mode & Transform**

Select a mapping mode from the filtered list (only modes compatible with your chosen source/target domains are shown), then fill in any mode-specific transform parameters.

After saving, click **Save & close** to persist and reload.

---

## Managing Existing Mappings

Click **Configure** → **Manage existing mappings** → select a mapping:

- **Edit mapping** — change any setting.
- **Delete mapping** — permanently remove it (confirmation required).
- **Toggle enable / disable** — flip the enabled flag without editing.
- **Duplicate mapping** — clone with a `(copy)` name suffix.
- **Back** — return to the main menu.

---

## Mapping Modes

### A. Boolean Mirror

Mirrors the on/off state of the source to the target.

- **Source domains:** `binary_sensor`, `switch`, `light`
- **Target domains:** `switch`, `light`

```
source ON  →  target turn_on
source OFF →  target turn_off
```

**Example:** `binary_sensor.sensor_hinten → switch.target_hinten`

---

### B. Numeric Pass-through

Parses the source's numeric state and writes it directly to a `number` entity.

- **Source domains:** `sensor`, `number`
- **Target domains:** `number`

**Example:** `sensor.temperature_x → number.some_target`

---

### C. Numeric Scaled

Linearly maps the source value from `[input_min, input_max]` to `[output_min, output_max]`. Supports clamp, invert, and round.

- **Source domains:** `sensor`, `number`
- **Target domains:** `number`, `light`

**Example:** `sensor.brightness_x → light.terrace` (0–1000 lux → 0–255 brightness)

---

### D. Numeric Threshold → Boolean

Turns the target **on** when `source ≥ threshold`, **off** otherwise.

- **Source domains:** `sensor`, `number`
- **Target domains:** `switch`, `light`

**Example:** `sensor.co2_ppm → switch.ventilation` (threshold 800)

---

### E. Light Mirror

Mirrors on/off and optionally brightness and colour temperature from one light to another.

- **Source domains:** `light`
- **Target domains:** `light`

**Example:** `light.scene_source → light.scene_target`

---

## Direction

### Unidirectional

State changes flow **source → target** only.

### Bidirectional

State changes flow in **both directions**. The integration listens to both entities and propagates changes on either side to the other.

**Loop prevention** (enabled by default): after writing to an entity, any state-change events from that entity within 2 seconds are treated as echoes and suppressed to prevent ping-pong loops.

---

## Retry (`retry_delay_seconds` / `max_retries`)

| Setting | Value | Behaviour |
|---|---|---|
| retry_delay_seconds | 0 | No retry |
| max_retries | 0 | No retry (even if delay > 0) |
| retry_delay_seconds | 5, max_retries=1 | Retry once after 5 s |
| retry_delay_seconds | 10, max_retries=3 | Up to 3 retries, 10 s apart |

---

## Dashboard Visibility

Every mapping creates these entities:

| Entity | Type | Description |
|---|---|---|
| `switch.<mapping>_enabled` | Switch | Enable / disable the mapping |
| `sensor.<mapping>_last_result` | Sensor | `success` / `failure` / `pending` |
| `sensor.<mapping>_success_count` | Sensor | Cumulative successes |
| `sensor.<mapping>_failure_count` | Sensor | Cumulative failures |
| `text.<mapping>_last_error` | Text | Last error message (read-only) |
| `button.<mapping>_run_once` | Button | Manually trigger the mapping |

---

## Services

| Service | Description |
|---|---|
| `ui_entity_mapper.reload` | Reload the integration |
| `ui_entity_mapper.enable_mapping` | Enable a mapping by UUID |
| `ui_entity_mapper.disable_mapping` | Disable a mapping by UUID |
| `ui_entity_mapper.run_mapping_once` | Manually trigger a mapping by UUID |
| `ui_entity_mapper.export_mappings` | Return all mappings as a service response |
| `ui_entity_mapper.import_mappings` | Bulk-import a list of mapping configs |

---

## Development & Testing

```bash
pip install pytest pytest-asyncio homeassistant
pytest tests/ -v
```

---

## Screenshots

<!-- Add screenshots of the config flow, entity list, and dashboard here -->

*Screenshot: Adding a mapping through the UI*

*Screenshot: Mapping entities on a dashboard*

*Screenshot: Diagnostics view*

---

## License

MIT