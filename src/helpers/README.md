# Helpers README

Shared utility functions used by `cogs`, organized into focused modules.

## Modules

| Module | Functions | Description |
|---|---|---|
| `date_utils.py` | `resolve_date`, `discord_timestamp` | Date parsing (MM/DD/YYYY) and Discord timestamp formatting |
| `material_utils.py` | `parse_materials`, `format_materials`, `validate_materials` | Material string parsing, embed formatting, and combined parse + validate |
| `validation_utils.py` | `is_numeric` | General-purpose validation helpers |
| `logger.py` | `setup_logging` | Centralized logging configuration (called once in `main.py`) |

All public functions are re-exported from `__init__.py` for convenience:
```python
from src.helpers import resolve_date, parse_materials
```
