# Views README

Shared view infrastructure used by all slash command cogs. No cog-specific logic lives here — only the reusable building blocks.

## `draft_view_base.py`

### Constants

| Name | Value | Description |
|---|---|---|
| `DRAFT_TTL_SECONDS` | `86400` | 1 day — how long a draft lives before expiry |
| `SWEEP_INTERVAL_MINS` | `60` | How often the background sweep runs |
| `DraftKey` | `tuple[str, str, str]` | `(user_id, channel_id, command_name)` — scopes drafts to one per user per channel per command |

---

### Expiry helpers

#### `is_expired(draft) -> bool`
Returns `True` if the draft's `created_at` is older than `DRAFT_TTL_SECONDS`.

#### `evict(store, key) -> None`
Removes the draft from the store and edits its Discord message to show an expiry notice. Silently handles `NotFound` and `HTTPException` (message deleted or uneditable). Safe to call from both lazy checks and the background sweep.

#### `draft_key(interaction, command_name) -> DraftKey`
Builds the store key from an interaction's `user.id`, `channel_id`, and the command name.

#### `check_existing_draft(interaction, store, command_name, label) -> bool`
Checks for an existing draft (evicting it first if expired). Returns `True` and sends an ephemeral error if a non-expired draft exists, `False` otherwise. Used by all four cog command handlers to deduplicate the draft-existence check.

---

### `SubmittedView`

Replaces `DraftView` once a request is finalised. Contains a single **⚡ Copy Text** button that sends the plain-text representation of the submitted request as an ephemeral message. Open to any user in the channel — not restricted to the original submitter.

No timeout.

---

### `AddMaterialModal`

A shared modal used by any command that has a materials list (`/changeorder`, `/matorder`). Accepts one or more materials in `Name - Quantity` format (one per line). Validates that all quantities are numeric before appending to the draft. On success, edits the draft embed in-place.

Constructed with `draft_key`, `store`, `draft_embed_fn`, and `view_cls` so it can update the correct draft and re-render the correct embed without any cog-specific code.

---

### `make_select_then_modal(options, *, other_label, placeholder) -> type`

Factory that returns a `View` base class showing a `Select` menu. On selection it calls `self.modal_factory(value)` and opens the returned modal.

**Usage — subclass and implement `modal_factory`:**
```python
class MySelectView(make_select_then_modal(MY_OPTIONS, placeholder="Pick one...")):
    async def modal_factory(self, value: str) -> discord.ui.Modal:
        if value == "Other":
            return MyModalOther()
        return MyModal(pre_selected=value)
```

The options list is baked in at class-creation time. To change options, pass a different list — no other changes needed. `other_label` (`"Other"` by default) is appended automatically if not already present.

---

### `make_draft_view(store, command_name, draft_embed_fn, final_embed_fn, plain_text_fn, *, has_materials, edit_modal_factory) -> type`

Factory that returns a `DraftView` class pre-wired to the given store and builder functions.

| Parameter | Description |
|---|---|
| `store` | The cog's module-level `drafts` dict |
| `command_name` | Used in log messages |
| `draft_embed_fn(user, draft)` | Builds the in-progress embed |
| `final_embed_fn(user, draft)` | Builds the submitted embed |
| `plain_text_fn(user, draft)` | Builds the plain-text copy string |
| `has_materials` | `True` → includes ➕ Add Material and ↩️ Undo Last buttons |
| `edit_modal_factory` | Optional. When provided, adds a ✏️ Edit button. Called as `factory(key, store, draft_embed_fn, view_cls)` — must return a `discord.ui.Modal` |

Returns one of two explicit class definitions:
- `DraftViewWithMaterials` — Add Material (row 0), Undo Last (row 0), [Edit (row 1)], Done (row N), Cancel (row N)
- `DraftViewSimple` — [Edit (row 0)], Done (row N), Cancel (row N)

The Edit button is only present when `edit_modal_factory` is provided. Row numbers adjust automatically.

Both classes share the same expiry guard (`_check_expired`), owner check (`interaction_check`), and cancel/done logic via inner closures to avoid duplication. No timeout — TTL is managed by `created_at` and the background sweep, not discord.py's built-in view timeout.

---

### `SweepMixin`

Mixin for `commands.Cog` subclasses that own a draft store. Starts a background `tasks.loop` that calls `evict()` on all expired drafts at `SWEEP_INTERVAL_MINS` cadence.

**Usage:**
```python
class MyCog(commands.Cog, SweepMixin):
    def __init__(self, bot):
        self.bot = bot
        self._store = drafts          # module-level dict
        self._command_name = COMMAND  # for log messages
        self._start_sweep()

    def cog_unload(self):
        self._stop_sweep()
```