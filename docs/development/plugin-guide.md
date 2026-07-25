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
from photo_archiver.application.ports.plugin import Plugin, PluginAction


class MyPlugin:
    @property
    def name(self) -> str:
        return "my_plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

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

    def execute_action(self, action_id: str) -> None:
        if action_id == "my_plugin.say_hello":
            logger.info("Hello from MyPlugin!")


plugin = MyPlugin()
```

### 3. Required Protocol Methods

| Method/Property | Description | Required |
|---|---|---|
| `name` | Stable unique identifier (`str`) | Yes |
| `version` | SemVer version string (`str`) | Yes |
| `enable()` | Activate plugin (acquire resources) | Yes |
| `disable()` | Deactivate plugin (release resources) | Yes |
| `actions()` | Return list of `PluginAction` descriptors | No (default: `[]`) |
| `execute_action(action_id)` | Execute a registered action | No (default: no-op) |

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
