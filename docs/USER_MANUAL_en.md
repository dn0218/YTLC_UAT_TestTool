# Preprod Telecom Operations Toolkit — Quick User Guide

A desktop toolkit for daily operations on the **pre-production (Preprod)** telecom environment. It connects to the Preprod OCS/CRM database, the billing SSH host, the job server, and the Redis cluster — everything is driven from one window with **six tabs**.

You don't need to log in to any backend system separately. Type an identifier, click a button, read the result in the console panel.

---

## 1. What This Tool Is

Each tab does one job: **you input an identifier, click the main (green) button, and the tool talks to the backend for you.** The table below tells you what each tab is for — that is all you need to know to get started.

| Tab | You input | Main button | What it does | Success looks like |
|-----|-----------|-------------|--------------|--------------------|
| **1. Invoice Generation** | Account ID / Number | Run Bill & Generate Invoice | Prepares recurring charges, runs the bill, verifies the invoice in the database | Dialog with the invoice number |
| **2. Contract End Date** | MSISDN (+ date) | Update / Deactivate | Views or changes the contract end date, or expires the contract | "Updated successfully" dialog |
| **3. MSISDN Clean '0'** | MSISDN ending in `0` | Remove Last '0' | Renames a number with a wrong trailing zero in all tables | "MSISDN updated" dialog |
| **4. Sales Invoice** | Account ID / Number | Trigger Sales Invoice | Triggers the sales e-invoice generation job on the job server | "Job triggered" dialog |
| **5. SIM Card Attribute** | ICCID | Query → double-click a row | Looks up a SIM card and edits its product-type attribute | Table refreshes with the new value |
| **6. Roaming Subscription Pass** | MSISDN + country | Validate → Execute in mdbtt | Inserts roaming-pass rows for every subscription of the number | "Rows inserted" dialog |

**Three universal rules that apply to every tab:**

1. **Wait for buttons to re-enable** before starting another action — disabled buttons mean the tool is working.
2. **Every write operation asks for confirmation first.** Check the identifier on screen carefully before clicking Yes.
3. **Keep the console (dark panel) log** until the operation is confirmed successful — it is the evidence for troubleshooting.

---

## 2. Quick Start

**Start the tool**

- Packaged build: double-click `PreprodTestTool.exe`. No installation needed.
- From source (maintainers only): `python main.py`.

**First launch — one-time setup**

1. On first launch the tool creates a template `config_ocs.json` next to the exe and closes with a message.
2. Normally you do NOT need to touch this file — it ships pre-configured for Preprod.
3. Only if your maintainer asks (e.g. the environment changed): edit the file in Notepad, save, restart the tool.
4. Never edit values starting with `enc:v1:` — they are encrypted credentials managed by maintainers.

**What you need**

- A PC that can reach the Preprod network (database, SSH host, job server, Redis).
- The identifier for your task: an Account ID/Number, MSISDN, or ICCID.

The window opens with six tabs on top, an input area, and a dark console panel at the bottom that logs every step.

---

## 3. Tabs At a Glance

Each tab follows the same pattern: **validate first, then execute.** The green Execute button unlocks only after validation passes.

### Tab 1 — Invoice Generation
1. Type the **Account ID or Number** → **Check Account** (must be active & postpaid; the cycle dropdown fills in).
2. Pick a billing cycle if you don't want the current one (a warning pops up for non-current cycles).
3. Click **Run Bill & Generate Invoice**. Takes 1–3 minutes (built-in waits are normal).
4. If asked *"No pre-charge found — continue?"*: **No** is the safe choice unless you know why.
5. If asked *"Null value detected — rerun?"*: usually answer **Yes** once; report it if it repeats.

### Tab 2 — Contract End Date
- **Check Agreement Status** → shows name, effective date, expiry date (warnings about state are non-blocking).
- **Update Expiry Date** → enter MSISDN + date as `YYYY-MM-DD` → done. A cache warning note may appear; the DB update itself succeeded.
- **Deactivate Contract** → sets dates to yesterday. Double-check the MSISDN — immediate effect.

### Tab 3 — MSISDN Clean '0'
1. Type an MSISDN **ending with `0`** → **Validate MSISDN**. Account/customer details appear for you to verify.
2. Review them carefully, then **Remove Last '0'** → confirm. The number is renamed in all tables.

### Tab 4 — Sales Invoice
1. **Check Account** → the **Type** label shows POSTPAID or PREPAID.
2. **Trigger Sales Invoice** → 200 = job triggered. Generation happens on the server side; verify results separately.

### Tab 5 — SIM Card Attribute
1. Type the **ICCID** → **Query** (or press Enter). Card info + product-type attributes appear.
2. **Double-click a row** → review current value → type the new value (JAVA/NATIVE) → **Confirm**. Table auto-refreshes with the verified value.

### Tab 6 — Roaming Subscription Pass
1. Type the **MSISDN** → **Validate MSISDN**. All subscriptions of the number are listed.
2. Pick the **Country** (KENYA / IRAN) → **Execute in mdbtt** → confirm. One insert per subscription; check the log for any FAILED SUBS_ID.

---

## 4. Troubleshooting Mini-FAQ

**Try these before reporting an issue — most reports stop here.**

| Symptom | What to do |
|---------|------------|
| Tool won't start; message about `config_ocs.json` | First-launch behavior. If it persists after restart, ask your maintainer for a fresh config file — do not edit it yourself. |
| "Database connection failed" / timeouts | You are probably off the Preprod network. Reconnect VPN/network and retry. If colleagues are fine, it's you; if everyone fails, it's the environment — report it as an environment issue, not a tool bug. |
| "Account is not in use" / "not Postpaid" (Tab 1) | Not a bug — business validation. Use an account that is active and postpaid. |
| "No pre-charge found — continue?" (Tab 1) | **No** is safe (bill not generated). Only choose Yes if you understand the missing charges. |
| "Null value detected — rerun?" (Tab 1) | Answer Yes once. If NULL appears again, keep the console log and report it. |
| "cache invalidation failed" note (Tab 2) | The contract update itself succeeded; only the cache cleanup failed. Report it as a **warning** with the log attached. |
| mdbtt timeout / FAILED SUBS_ID (Tab 6) | Check the operation log tail — the last 12 console lines usually show the SQL error. Retry once; if it repeats, report with the log. |
| Window "frozen" | Built-in waits (10 s / 30 s) are normal during bill runs. Check whether a dialog is hiding behind the window first. |

Still stuck? → Go to Section 5 and follow the feedback process.

---

## 5. Issue Feedback Process

**Read this before reporting anything.** Reports that do not follow this process will NOT be accepted. This is not bureaucracy — a complete report is answered in one batch cycle; an incomplete one costs everyone a week of back-and-forth.

### 5.1 Where to submit

- Submit via the **Teams feedback channel** to the **designated tester** of your team. Do NOT send reports directly to developers' private chats.
- Testers **collect all reports during the week** and submit them as one batch. Maintainers process batches **1–2 times per week**.
- Consequence: a report filed on Monday may be answered at the weekly batch — plan your testing accordingly.

### 5.2 Issue template (copy, fill in, attach — missing fields = not accepted)

```markdown
## Issue Report (all fields required)
- [ ] Tool version — exe "Date modified" (right-click PreprodTestTool.exe → Properties → Details):
- [ ] Tab: □ Invoice Generation □ Contract End Date □ MSISDN Clean '0'
      □ Sales Invoice □ SIM Card Attribute □ Roaming Pass
- [ ] Steps to reproduce (1 / 2 / 3 …, exact inputs, e.g. account ID used):
- [ ] Expected result:
- [ ] Actual result (exact error text / dialog title):
- [ ] Console log screenshot (REQUIRED — the dark panel, scroll to the error):
- [ ] Did you check Section 4 FAQ first? □ Yes
- [ ] Reporter + date:
```

**How to fill "Tool version":** right-click `PreprodTestTool.exe` → **Properties → Details → Date modified** — type that date. Two bugs with different dates are different builds; without it we cannot reproduce.

### 5.3 Acceptance criteria (a report is accepted only when ALL hold)

1. Submitted through the Teams channel to the designated tester (not private chats).
2. Every template field filled in — including the version date and the FAQ checkbox.
3. Console log screenshot attached, showing the error (not just the input screen).
4. Reproducible: the steps, with the exact identifier used, lead to the problem.
5. Not already reported — check the channel's pinned "Known Issues" list before submitting.

### 5.4 NOT accepted (any one of these = rejected, no reply)

1. Verbal / phone / private-chat reports — no record, no tracking.
2. Missing console log or screenshots (**"it just failed" is not a report**).
3. Missing steps to reproduce, or steps that cannot be repeated.
4. **"It doesn't work"** with no error text or expected-vs-actual comparison.
5. Issue already listed in the pinned Known Issues list.
6. Environment problems (DB down, network off, VPN) reported as tool bugs — see Section 4.


### 5.5 Status flow & response times

| Status | Meaning | Who acts | Expected within |
|--------|---------|----------|-----------------|
| **New** | Batch received by maintainer | Maintainer | Next batch day (1–2×/week) |
| **Triaged** | Confirmed valid, priority set | Maintainer | Same batch cycle, with a first reply |
| **Info needed** | Report incomplete → back to reporter | **You** | Reply within 3 working days, or the issue is closed |
| **Fixing** | Fix in progress | Maintainer | Announced ETA in the channel |
| **Fixed** | New build posted in the channel | Maintainer | — |
| **Closed** | Verified by reporter or auto-closed | You | Verify in the new build within 5 working days |

**One report = one issue.** If you found three problems, submit three copies of the template.

---

## 6. Safety Rules

1. **Preprod only.** This tool writes directly to the database it is configured for. Never point it at production.
2. **Guard the config file.** `config_ocs.json` contains (encrypted) credentials — do not share, upload, or screenshot it.
3. **One operation at a time.** Wait for buttons to re-enable; never leave a bill run half-finished.
4. **Keep the console log** until the result is confirmed — and attach it to every issue report (Section 5).
5. **When unsure, ask before clicking** — in the Teams channel, before the operation, not after.
