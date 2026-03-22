# Cogs README

Cogs are Discord bot modules, each containing one slash command. The cog imports shared helpers from `helpers/`.

## `/changeorder` — Multi-Step Flow 

1. User runs `/changeorder`
   - If the user already has an active draft in this channel, an ephemeral error is returned
2. **Step 1 modal** collects:
   - **Date Requested** — MM/DD/YYYY, optional (defaults to today)
   - **Scope Added** — freeform description of work being added
3. A draft embed is posted with four buttons:
   - ➕ **Add Material** — opens a modal to add multiple material (name + numeric quantity, one per line separated by " - ")
   - ↩️ **Undo Last** — removes the most recently added material
   - ✅ **Done** — finalizes the draft, posts the submitted embed, disables all buttons except **Copy Text**
   - 🗑️ **Cancel** — discards the draft, disables all buttons4. Once submitted, a **Copy Text** button remains active so anyone in the channel can copy a plain-text version of the change order
5. Only the user who created the draft can interact with the draft buttons
6. Draft expires after **1 day** of inactivity

### Draft Storage
- Drafts are stored **in-memory** in a `dict` keyed by `(user_id, channel_id)`
- A user can have active drafts across multiple channels simultaneously
- Drafts do **not** persist across bot restarts
- A background sweep runs every 1 hours to evict stale drafts and update their Discord messages