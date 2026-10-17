# Cards and Compliance in the Android app

The web CRM already has a **Compliance** tab (card, invoice and payment proof per store per month). The phone now offers the same thing. Nothing new was built on the server: the app calls the **existing** `/compliance` routes, so records, permissions, history and rules are shared with the web CRM.

## Why employees could not use it before
Not a permission problem. Employees already hold `compliance.upload` (a default grant), and the server already limits the list to their own stores. The app simply had **no screen and no API client** for Compliance. Now:

| Where | What |
|---|---|
| **Compliance** tab (bottom bar) | Shown only when the person has `compliance.upload` or `compliance.manage`, the same permissions the web route uses. The server checks them again on every request, so hiding or showing the tab is never the security. |
| Dashboard (Today) | A **Store cards** tile ("Upload a card photo") and a **Compliance** tile ("62% complete this month"). |
| **Store cards** screen | The same stores and records, showing only the card slot, with **Upload card photo** on every row. |
| Store page | The three slots (Card, Invoice, Payment proof) for a month: status, upload time, view, upload new, history, remove. |

## What a person can do (the same as on the web page)
- Choose the month (the same months the web page offers), search by store name or code, filter (nothing logged / partly done / complete, or "missing card").
- **View** a document at full size, or open a PDF in the phone's own viewer. Earlier versions open from **History**.
- **Upload / upload new**: take a photo, choose from the gallery, or choose a PDF. Preview, remove and replace before sending; progress bar while sending; a clear success or failure message; **Try again** keeps the chosen photo.
- **Remove** archives the document like the web page does: the file stays stored and uploading again brings the same record back.
- Not offered to employees on the web either, and not on the phone: clearing a bill (`accounts.clear`), bulk upload and summary PDF.

## How an upload works
1. The photo is shrunk **on the phone** (upright, longest side from the server's policy, JPEG at the server's quality). It is only done if the photo is not already small; any failure falls back to the original. A 2-5 MB camera photo becomes about 0.2-0.4 MB.
2. `POST /compliance/upload` (multipart) with an `Idempotency-Key`. The key belongs to the chosen files: a retry of the same selection reuses it, so the server returns the first result and **never creates a second version**. A different selection gets a new key.
3. The server checks the type and size, shrinks the photo again if needed, strips GPS, writes the file to the private bucket under a unique key, **confirms the stored size**, and only then creates the record. The app shows "Saved" only after that answer.
4. Several photos of one document become one PDF; a PDF goes on its own. Each upload is a new **version**; the earlier file is never overwritten or deleted.
5. A failed or interrupted upload leaves no record. The message comes from the server (too big, not an image, storage busy...).

The limits are read from `GET /uploads/policy` (today: photos stored at most 1 MB, up to 12 MB accepted, PDFs at most 2 MB); nothing is hard-coded in the app except the same defaults used until the server answers. The server enforces all of them regardless of the app.

## Viewing files
The app asks the server for a short-lived link (`GET /compliance/{id}/url`, valid 5 minutes) and loads the file straight from the private bucket; if the server returns no link it fetches the file through the authenticated route. Files are requested only when someone opens them (the card photo on a store page loads a small preview). No permanent URL or credential is stored on the phone.

## Backend changes
**None.** No migration. One observation: the list route returns `uploaded_by: null` (the field exists but the list does not fill it in; only the upload answer does). The app shows "by <name>" whenever the server supplies it. Filling it in the list route is a small, additive server change (a name lookup per page) if you want uploader names on the phone; it was not made because it is not essential.

## Tests
- `backend/tests/test_mobile_compliance_contract.py` (9): an employee sees only their stores; no permission means 403 and no login means 401; the list gives the app what it needs; the web and the phone see the same records both ways; a retry with the same key makes no second version; a new upload keeps the earlier file and both open; another store's files stay out of reach even with the right id; remove and restore; the policy matches what the server enforces.
- `mobile/src/lib/compliance.test.ts` (13): the upload rules (PDF alone, PDF limit, photo ceiling, file count, policy-driven limits), selection wording, when a photo is shrunk, resizing maths, slot badges, retry signature.
- A scripted run of the phone's exact sequence against a local server (sign in, permissions, list, upload, retry, view, history, remove, restore, access checks): 23 of 23 passed.

## Not tested here: needs a phone
No Android device or emulator was available. Before sending to employees, on one real phone (preferably a small, mid-range one):
1. Sign in as an employee: the Compliance tab and the two dashboard tiles are visible; as a person without `compliance.upload` they are not.
2. Compliance tab: month chips, search with the keyboard open (the list stays usable), filters, tap a store.
3. Store page: **Take photo** (grant the camera permission), preview, tap the preview to see it larger, remove, replace, **Upload**; watch the progress bar; see "Saved"; **View** it; open **History**.
4. Turn on aeroplane mode mid-upload: a clear message, **Try again** after reconnecting, and exactly one version afterwards.
5. **Gallery** (several photos: merged into one PDF) and **PDF** (a PDF over 2 MB shows the size message).
6. Open the same store on the web CRM: the same card, upload time and history.
7. Rotate nothing (the app is portrait only), try a small phone and a large phone, the gesture and three-button navigation bars, and the back button from every screen.
