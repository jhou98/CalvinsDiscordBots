# Cogs README

Cogs are Discord bot modules, each containing one slash command. All cogs import shared helpers from `helpers/`, models from `models/`, and view infrastructure from `views/`.

## `/changeorder`

**Flow:** Modal → Draft embed with buttons

1. User runs `/changeorder`
   - If the user already has an active draft in this channel, an ephemeral error is returned
2. A modal opens with three fields:
   - **Date Requested** — MM/DD/YYYY, optional (defaults to today)
   - **Scope Added** — freeform description of work being added
   - **Materials** — optional bulk entry upfront (Name - Quantity, one per line)
3. A draft embed is posted with four buttons:
   - ➕ **Add Material** — opens a modal to add one or more materials (Name - Quantity, one per line)
   - ↩️ **Undo Last** — removes the most recently added material
   - ✅ **Done** — requires at least one material; finalises and posts the submitted embed
   - 🗑️ **Cancel** — discards the draft

---

## `/inspectionreq`

**Flow:** Ephemeral select → Step 1 modal → Ephemeral continue button → Step 2 modal → Draft embed with buttons

1. User runs `/inspectionreq`
   - If the user already has an active draft in this channel, an ephemeral error is returned
2. An ephemeral **Select menu** appears for the user to pick an inspection type
   - Selecting a named type opens Step 1 with 3 fields
   - Selecting **Other** opens Step 1 with an extra free-text type field (4 fields)
3. **Step 1 modal** collects:
   - **Inspection Date** — MM/DD/YYYY
   - **Date Requested** — MM/DD/YYYY, optional (defaults to today)
   - **AM / PM Preference**
   - **Inspection Type (describe)** — only shown when Other is selected
4. An ephemeral **Continue →** button appears (Discord does not allow a modal to open another modal directly)
5. **Step 2 modal** collects:
   - **Site Contact Name**
   - **Site Contact Phone** — validated (7–15 digits)
6. A draft embed is posted with three buttons:
   - ✏️ **Edit** — re-opens a modal to modify Inspection Date, Site Contact Name, Site Contact Phone, and AM/PM. Date Requested and Inspection Type are **not** editable.
   - ✅ **Done** — finalises and posts the submitted embed
   - 🗑️ **Cancel** — discards the draft

To add or rename inspection types, edit `INSPECTION_TYPES` at the top of `inspection_req.py`. `Other` is always appended automatically.

---

## `/matorder`

**Flow:** Step 1 modal → Ephemeral continue button → Step 2 modal → Draft embed with buttons

1. User runs `/matorder`
   - If the user already has an active draft in this channel, an ephemeral error is returned
2. **Step 1 modal** opens with five fields:
   - **Date Requested** — MM/DD/YYYY, optional (defaults to today)
   - **Requested By** — name of the person requesting
   - **Required Date** — MM/DD/YYYY
   - **Site Contact Name**
   - **Site Contact Phone** — validated (7–15 digits)
3. An ephemeral **Continue →** button appears
4. **Step 2 modal** opens with two fields:
   - **Delivery Notes** — optional freeform notes
   - **Materials** — optional bulk entry (Name - Quantity, one per line)
5. A draft embed is posted with four buttons:
   - ➕ **Add Material** — opens a modal to add one or more materials (Name - Quantity, one per line)
   - ↩️ **Undo Last** — removes the most recently added material
   - ✅ **Done** — requires at least one material; finalises and posts the submitted embed
   - 🗑️ **Cancel** — discards the draft

---

## `/rfi` (Request for Information)

**Flow:** Ephemeral select → Step 1 modal → Ephemeral continue button → Step 2 modal → Draft embed with buttons

RFI has 7 fields which exceeds Discord's 5-field modal limit, and uses a select menu for impact level, so the flow is split across two modals.

1. User runs `/rfi`
   - If the user already has an active draft in this channel, an ephemeral error is returned
2. An ephemeral **Select menu** appears for the user to pick an impact level
   - Selecting a named level opens Step 1 modal
   - Selecting **Other** opens Step 1 with an extra free-text impact field
3. **Step 1 modal** collects:
   - **Date Requested** — MM/DD/YYYY, optional (defaults to today)
   - **Requested By** — name of person requesting
   - **Required By** — MM/DD/YYYY
   - **Impact (describe)** — only shown when Other is selected
4. An ephemeral **Continue →** button appears (Discord does not allow a modal to open another modal directly)
5. **Step 2 modal** collects:
   - **Question** — 1–2 sentences, clear and specific
   - **Issue / Background** — why this is being asked
   - **Proposed Solution** — optional
6. A draft embed is posted with **Done** and **Cancel** buttons

To add or rename impact levels, edit `RFI_IMPACT_OPTIONS` at the top of `rfi.py`. `Other` is always appended automatically.

---

## Shared behaviours (all commands)

- Only the user who created the draft can interact with its buttons
- Drafts expire after **1 day** of inactivity
- A background sweep runs every **60 minutes** to evict stale drafts and update their Discord messages
- Lazy expiry checks also run on every button press and on command entry
- A user can have one active draft **per command per channel** simultaneously (e.g. `/matorder` and `/rfi` can both be active in the same channel)
- All submitted embeds include a **⚡ Copy Text** button open to anyone in the channel

### Draft Storage
- Drafts are stored **in-memory** in a `dict` keyed by `(user_id, channel_id, command_name)`
- Drafts do **not** persist across bot restarts