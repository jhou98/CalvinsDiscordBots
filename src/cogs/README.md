# Cogs README

Cogs are Discord bot modules, each containing one slash command. Both cogs import shared helpers from `helpers/`.

## `/changeorder` — Single Modal Flow 

1. User runs `/changeorder`
2. A single modal opens with three fields:
   - **Date Requested** — MM/DD/YYYY, optional (defaults to today)
   - **Scope Added** — freeform description of work being added
   - **Materials** — freeform text, one item per line, format: `Name - Quantity`
3. On submit, materials are parsed and validated — any malformed lines return an ephemeral error asking the user to retry
4. On success, a formatted embed is posted to the channel

## `/changeorderpro` — Multi-Step Flow 

1. User runs `/changeorderpro`
   - If the user already has an active draft, an ephemeral error is returned
2. **Step 1 modal** collects:
   - **Date Requested** — MM/DD/YYYY, optional (defaults to today)
   - **Scope Added** — freeform description of work being added
3. A draft embed is posted with four buttons:
   - ➕ **Add Material** — opens a modal to add one material (name + numeric quantity)
   - ↩️ **Undo Last** — removes the most recently added material
   - ✅ **Done** — finalizes the draft, posts the submitted embed, disables all buttons
   - 🗑️ **Cancel** — discards the draft, disables all buttons
4. Only the user who created the draft can interact with its buttons
5. Draft expires after **1 hour**

### Draft Storage
- Drafts are stored **in-memory** in a `dict` keyed by user ID
- Drafts do **not** persist across bot restarts