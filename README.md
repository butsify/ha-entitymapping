# UI Entity Mapper

A HACS-installable Home Assistant custom integration that lets you create
rule-based mappings between entities entirely through the UI — no YAML
automations required.

---

## Features

- **Full UI management** — create, edit, and delete mappings directly from Settings → Devices & Services.
- **Five mapping modes** — boolean mirror, numeric pass-through, numeric scaled, numeric threshold, and light mirror.
- **Lock entity support** — boolean mirror and numeric threshold modes support `lock` as source and target.
- **Bidirectional support** — propagate state changes in both directions with built-in ping-pong loop prevention.
- **Configurable retry** — retry a failed command up to *N* times after a configurable delay.
- **Per-mapping dashboard device** — each mapping appears as its own device with enabled-switch, last-result sensor, success/failure counters, last-error text, and a run-once button.
- **Services** — reload, enable, disable, run-once, export, and import mappings programmatically.

---

## Installation via HACS

1. Open HACS in your Home Assistant instance.
2. Click the **⋮ menu** → **Custom repositories**.
3. Add `https://github.com/butsify/ha-entitymapping` as type **Integration**.
4. Search for **UI Entity Mapper** and click **Download**.
5. Restart Home Assistant.

---

## Creating a Mapping

1. Go to **Settings → Devices & Services**.
2. Find the **UI Entity Mapper** integration card and click **+ Add service**.
3. Fill in the two-step form:

**Step 1 — Basic settings**

| Field | Description |
|---|---|
| Mapping name | Human-readable label shown on the device card |
| Source entity | The entity whose state changes drive the mapping |
| Target entity | The entity that receives commands |
| Direction | `Unidirectional (source -> target)` or `Bidirectional (source <-> target)` |
| Enabled | Toggle the mapping on/off without deleting it |
| Prevent feedback loops | Suppresses echo events after our own writes (recommended `on`) |
| Retry delay (s) | Seconds to wait before retrying if the target did not reach the desired state (`0` = no retry) |
| Max retries | Number of retry attempts (`0` disables retries even if a delay is set) |

**Step 2 — Mode & Transform**

Select a mapping mode from the filtered list (only modes compatible with your chosen source/target domains are shown), then fill in any mode-specific transform parameters.

---

## Managing Existing Mappings

Each mapping appears as a service under the **UI Entity Mapper** integration card:

- **Edit** (pencil icon) — opens the two-step form pre-filled with current values.
- **Delete** (three-dot menu → Delete) — permanently removes the mapping and all its entities.
- **Enable/Disable** — use the `Enabled` switch on the mapping's device card, or the `enabled` field when editing.

---

## Mapping Modes

### A. Boolean Mirror

Mirrors the on/off (or locked/unlocked) state of the source to the target.

- **Source domains:** `binary_sensor`, `switch`, `light`, `lock`
- **Target domains:** `switch`, `light`, `lock`
- **Transform:** `Invert output` — reverses the state before writing

```
source ON     →  target turn_on  (or lock)
source OFF    →  target turn_off (or unlock)
source locked →  target lock
```

---

### B. Numeric Pass-through

Parses the source's numeric state and writes it directly to a `number` entity.

- **Source domains:** `sensor`, `number`
- **Target domains:** `number`

---

### C. Numeric Scaled

Linearly maps the source value from `[input_min, input_max]` to `[output_min, output_max]`.

- **Source domains:** `sensor`, `number`
- **Target domains:** `number`, `light`
- **Transform options:** `Invert output`, `Round to nearest integer`

**Example:** `sensor.brightness_x → light.terrace` (0–1000 lux → 0–255 brightness)

---

### D. Numeric Threshold

Turns the target **on** when `source >= threshold`, **off** otherwise.

- **Source domains:** `sensor`, `number`
- **Target domains:** `switch`, `light`, `lock`

**Example:** `sensor.co2_ppm → switch.ventilation` (threshold 800)

---

### E. Light Mirror

Mirrors on/off and optionally brightness and colour temperature from one light to another.

- **Source domains:** `light`
- **Target domains:** `light`
- **Transform options:** `Mirror brightness`, `Mirror colour temperature`

---

## Direction

### Unidirectional

State changes flow **source → target** only.

### Bidirectional

State changes flow in **both directions**. The integration listens to both entities and propagates changes on either side to the other.

**Loop prevention** (enabled by default): after writing to an entity, any state-change events from that entity within 2 seconds are treated as echoes and suppressed.

---

## Retry

| retry_delay_seconds | max_retries | Behaviour |
|---|---|---|
| 0 | any | No retry |
| any | 0 | No retry |
| 5 | 1 | Retry once after 5 s |
| 10 | 3 | Up to 3 retries, 10 s apart |

---

## Per-mapping Device Entities

Every mapping creates a device with these entities:

| Entity | Type | Description |
|---|---|---|
| `switch.<name>_enabled` | Switch (Config) | Enable / disable the mapping |
| `sensor.<name>_last_result` | Sensor | `success` / `failure` / `pending` |
| `sensor.<name>_success_count` | Sensor | Cumulative successes |
| `sensor.<name>_failure_count` | Sensor | Cumulative failures |
| `text.<name>_last_error` | Text (Diagnostic) | Last error message (read-only) |
| `button.<name>_run_once` | Button (Config) | Manually trigger the mapping |

---

## Services

| Service | Description |
|---|---|
| `ui_entity_mapper.reload` | Reload all mapping entries |
| `ui_entity_mapper.enable_mapping` | Enable a mapping by its UUID |
| `ui_entity_mapper.disable_mapping` | Disable a mapping by its UUID |
| `ui_entity_mapper.run_mapping_once` | Manually trigger a mapping by its UUID |
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