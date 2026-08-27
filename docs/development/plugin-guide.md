# PhotoArchiver Plugin Development Guide

## Overview

The PhotoArchiver plugin system (Step 15) lets third-party code extend the desktop application with custom menu actions, data processing hooks, and automation features. The system follows a **safe-loading** architecture: a faulty plugin never crashes the host application.

### Dependency Rule

- **Plugins → Application, Common** (DEP-060)
- Plugins MUST NOT import from `infrastructure/`, `presentation/`, `workers/`, or `ai/` directly
- Plugins MUST NOT modify internal project modules (DEP-061)
- Plugins communicate only through public interfaces (DEP-062)

## Creating a Plugin

### 1. File Layout

Each plugin is a single Python file placed in `examples/plugins/` (or a custom plugin directory). The file must export a module-level variable called `plugin` that implements the `Plugin` protocol (defined in `photo_archiver.application.ports.plugin`).

```
examples/plugins/
  └── my_plugin.py
```

### 2. Minimum Implementation

```python
from loguru import logger

from photo_archiver.application.dtos.plugin_action_result import ActionResult, noop, success
from photo_archiver.application.ports.plugin import PluginAction
from photo_archiver.application.ports.plugin_context import PluginContext


class MyPlugin:
    """ContextAwarePlugin-style plugin (new standard since Phase 1, ADR-026)."""

    @property
    def name(self) -> str:
        return "my_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    def set_context(self, context: PluginContext) -> None:
        self._context = context  # store for use in execute_action()

    def enable(self) -> None:
        logger.info("MyPlugin enabled")

    def disable(self) -> None:
        logger.info("MyPlugin disabled")

    def actions(self) -> list[PluginAction]:
        return [
            PluginAction(
                id="my_plugin.say_hello",
                label="Say Hello",
                tooltip="Greet from MyPlugin",
            ),
        ]

    def execute_action(self, action_id: str) -> ActionResult:
        if action_id == "my_plugin.say_hello":
            logger.info("Hello from MyPlugin!")
            return success(message="Hello from MyPlugin!")
        return noop()


plugin = MyPlugin()
```

### 3. Required Protocol Methods

| Method/Property | Description | Required |
|---|---|---|
| `name` | Stable unique identifier (`str`) | Yes |
| `version` | SemVer version string (`str`) | Yes |
| `set_context(context)` | Inject host-provided read-only `PluginContext` (new standard, ADR-026) | Yes |
| `enable()` | Activate plugin (acquire resources)——context注入改走 `set_context` (ADR-026) | Yes |
| `disable()` | Deactivate plugin (release resources) | Yes |
| `actions()` | Return list of `PluginAction` descriptors | No (default: `[]`) |
| `execute_action(action_id)` | Execute a registered action, returning an `ActionResult` (success / failure / noop) | No (default: noop) |

### 4. PluginAction

A `PluginAction` describes one menu item the plugin wants to register:

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Stable action identifier (e.g. `"my_plugin.do_thing"`) |
| `label` | `str` | Menu/toolbar label shown to the user |
| `tooltip` | `str` | Optional status-bar tooltip |
| `icon_name` | `str` | Optional icon resource name (reserved) |

### 5. Error Handling

- If a plugin file cannot be imported, the loader logs a warning and skips it
- If `enable()` raises, the plugin is logged and marked disabled
- If `execute_action()` raises, the error is shown in a message box but the app continues

### 6. PluginContext Facade

The host injects the `PluginContext` facade through `set_context(context)`
(new standard since Phase 1 / ADR-026; the legacy `enable(context)` dispatch
was REMOVED in v2.0.0 per ADR-030 — plugins carrying the old signature with a
required positional parameter fail to enable and are skipped with a logged
error; plugins whose old signature merely defaults the parameter (e.g.
`context=None`) still enable via the no-arg call but never receive the host
context — misbehavior surfaces later at `execute_action()` time).
Plugins store it and use it to
access a limited Application Service subset:

```python
def set_context(self, context: PluginContext) -> None:
    self._context = context  # keep for use in execute_action()
```

Exposed capabilities:

| Method | Kind | Description |
|---|---|---|
| `search_photos(query)` | Read | Query photos by person / match status / capture-date range |
| `detect_duplicates()` | Read | Return the duplicate-photo report across all loaded photos |
| `import_people(command)` | Write | Import person entities from plugin-supplied rows (Phase 3, ADR-028) |

Current limits:

- `import_people` is the **only** write capability (ADR-028 裁决点 1=A);
  export was **closed as YAGNI** by ADR-030 — a genuine future use case
  requires a fresh design gate.
- There is **no host approval gate** yet (ADR-028 裁决点 2=A): plugins call the
  context directly and the host renders the returned ActionResult.
- Plugins access business data only through the context — never through
  Repository, UnitOfWork, Archive services, WorkerExecutor, or the full
  `ApplicationContext`.
- `execute_action()` returns an `ActionResult`; the **host renders** it. Plugins
  MUST NOT touch UI widgets, the filesystem, or Infrastructure directly.
- A plugin that fails to load or enable never crashes the host (logged + skipped).
- The plugin system is **not a security sandbox** — it is a trusted local
  Python plugin model. Only load plugins you trust.

## Write Capability: import_people (Phase 3, ADR-028)

Plugins can write person entities through the context without touching files,
repositories, or Domain types (双向 DTO 脱 Domain，ADR-028 裁决点 3=C):

```python
from photo_archiver.application.dtos.plugin_context import (
    PluginImportPeopleCommand,
    PluginImportPersonRow,
)

rows = (
    PluginImportPersonRow(name="张三", identity="DEMO-001", department="Demo"),
    PluginImportPersonRow(name="李四"),  # identity optional
)
result = self._context.import_people(PluginImportPeopleCommand(rows=rows))

result.imported_count        # newly persisted persons
result.skipped_count         # duplicate-identity rows skipped by dedup
result.imported_person_ids   # tuple[str, ...] — str ids, NOT UUID (de-Domain)
result.errors                # tuple[str, ...] row-level messages like "row 3: ..."
result.succeeded             # property: True when errors is empty
```

Behavior notes:

- `row_number` is filled by the host service from tuple order (1-based); plugin
  rows do not carry it.
- Rows whose `identity` already exists are **skipped**; re-running an import is
  therefore idempotent **only when every row carries a stable identity** — rows
  without `identity` are never deduplicated and insert again on each run.
- Invalid rows (e.g. blank name) surface as per-row error strings; one bad row
  never aborts the batch.
- A working example lives in `examples/plugins/import_people_demo_plugin.py`
  (toolbar action "Import People (Demo)", rendered through the generic
  `PluginReportDialog`).

## Testing a Plugin

Run the plugin loader unit tests:

```bash
pytest tests/unit/plugins/
```

The example plugin `examples/plugins/hello_plugin.py` can be verified by loading it in a Python shell:

```python
from photo_archiver.plugins import PluginRegistry
from pathlib import Path

registry = PluginRegistry()
registry.load_from_path(Path("examples/plugins"))
registry.enable_all()
print(registry.plugins)   # Should show "hello" plugin
```

## Lifecycle Summary

```
loader.load_from_path(path)   # Discover & import
    ↓
loader.enable_all()           # Call plugin.enable() for each
    ↓
    [User uses menu actions]  # execute_action() dispatched
    ↓
loader.disable_all()          # Call plugin.disable() for each
```
