# Raising tickets from a Google Form / Sheet (Apps Script)

Tickets your Google Script collects can appear in the CRM's **Tickets** page automatically. The script sends each new
ticket to the CRM; the CRM routes it to the right region (like any ticket), and admins see it with the others.
A ticket from Google shows a **Google** tag and the reporter's name.

## 1. Switch it on (once)

1. Make up a long secret key, e.g. run `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. On Render → **veekay-api → Environment**, add `TICKET_WEBHOOK_KEY` = that key. Save (the service redeploys).
   Locally, put the same line in `backend/.env` and restart the backend.
3. Never put this key in a public place. Anyone with it can create tickets.

The address your script calls is:

```
https://<your-api>/api/v1/integrations/tickets        (locally: http://localhost:8000/api/v1/integrations/tickets)
```

## 2. What the script sends

A `POST` with header `X-Integration-Key: <your key>` and JSON:

| Field | Required | Meaning |
| --- | --- | --- |
| `external_id` | yes | A unique id for this ticket (the form response id or the sheet row). **Sending it twice never makes a duplicate**, so retries are safe. |
| `store_code` | one of these two | The store's outlet code as shown in the CRM (e.g. `3817`, `ES117`). |
| `platform` | no | Tickets are Blinkit-only for now: leave it out (it defaults to `blinkit`); `zepto` is refused. |
| `store_name` | one of these two | The store's name as shown in the CRM. Used when there is no code, or the code isn't found. Matching ignores case and extra spaces, and accepts part of the name if only one store fits. |
| `title` | yes | Short summary (3–160 characters). |
| `category` | no | Free text is fine: "Water arrived late", "Bottles damaged", "Short supply", "Invoice problem"… It is matched to Late delivery / No delivery / Short supply / Water quality / Damaged / Billing, otherwise *Other*. |
| `priority` | no | "Urgent", "High", "Medium", "Low" (default Medium). |
| `description` | no | Details. |
| `reporter` | no | Who raised it (name / phone / email) — shown on the ticket. |
| `raised_at` | no | ISO time the issue was raised; defaults to now. |

Replies: `201` created, `200` already existed (same `external_id`), `401` wrong key, `422` store not found (the message says which code),
`503` the key isn't configured on the server.

## 3. Apps Script (paste into the script attached to your Sheet or Form)

```javascript
const CRM_URL = "https://<your-api>/api/v1/integrations/tickets";
const CRM_KEY = "<your TICKET_WEBHOOK_KEY>";   // better: Project Settings > Script properties

// Google Form -> "On form submit" trigger. Change the question titles to match your form.
function onFormSubmit(e) {
  const r = e.namedValues;                       // { "Question title": ["answer"] }
  const get = (k) => (r[k] && r[k][0]) || "";
  sendTicket({
    external_id: "form-" + e.range.getRow(),     // unique per response (row number is fine for one sheet)
    store_code: get("Store code"),
    platform: get("Platform").toLowerCase(),     // "Blinkit" / "Zepto"
    category: get("Issue type"),
    priority: get("Priority"),
    title: get("Issue type") + " - " + get("Store code"),
    description: get("Details"),
    reporter: get("Your name") + " " + get("Phone"),
  });
}

// Or: run on a time trigger over a Sheet, sending rows that have no "CRM ticket" value yet (column H here).
function sendNewRows() {
  const sh = SpreadsheetApp.getActiveSheet();
  const rows = sh.getDataRange().getValues();
  for (let i = 1; i < rows.length; i++) {
    if (rows[i][7]) continue;                    // already sent
    const res = sendTicket({
      external_id: "sheet-" + sh.getSheetId() + "-" + (i + 1),
      store_code: String(rows[i][1]), platform: String(rows[i][2]).toLowerCase(),
      category: String(rows[i][3]), priority: String(rows[i][4]),
      title: String(rows[i][3]) + " - " + rows[i][1], description: String(rows[i][5]), reporter: String(rows[i][6]),
    });
    if (res && res.ticket) sh.getRange(i + 1, 8).setValue(res.ticket);   // e.g. TK-0042
  }
}

function sendTicket(payload) {
  const resp = UrlFetchApp.fetch(CRM_URL, {
    method: "post",
    contentType: "application/json",
    headers: { "X-Integration-Key": CRM_KEY },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });
  const code = resp.getResponseCode();
  const body = resp.getContentText();
  if (code === 200 || code === 201) return JSON.parse(body);
  console.error("CRM rejected the ticket (" + code + "): " + body);   // e.g. 422 "No store with code ..."
  return null;
}
```

Test it first with one row. A rejected ticket (wrong store code) is logged in **Apps Script → Executions** and can simply be retried
after the code is fixed — a ticket that was already accepted is never duplicated.

## Notes

- The CRM does **not** read your Google Sheet; the script pushes to the CRM, so nothing needs to be shared publicly.
- Tickets from Google have no CRM user as author; the `reporter` text is shown instead.
- To send a ticket's later updates back to Google, the CRM would need a separate callback — not built.
