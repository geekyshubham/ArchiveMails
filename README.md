# ArchiveMails

A local email archive reader with Outlook-cache recovery, folder imports, recipient account views, and a VibeRouter research chatbot.

**This repository contains code only.** No emails, attachments, cache snapshots, account credentials, generated exports, or real mailbox fixtures are included.

## Start the app

Requires Python 3.10 or newer. Reading EML archives and running the viewer use Python’s standard library.

```sh
git clone https://github.com/Geekyshubham/ArchiveMails.git
cd ArchiveMails
python3 serve.py --open
```

The app starts empty at http://127.0.0.1:8765. Click **Import folder** to add mail. macOS users can also run `Open Mail Archive.command`; Windows users can run `Open Mail Archive.bat` with Python installed. Stop the server with Ctrl+C. Use `--port 8766` if the default port is occupied.

## Import mail

- **Choose folder:** select a folder containing `.eml` files or a copied New Outlook `Olk` folder.
- **Choose ZIP / EML:** import individual EML files, an EML ZIP, or `Olk.zip`.
- Files are uploaded to the local server, processed in the background, and added to the current archive.
- Identical file hashes, existing Outlook message IDs, and matching Internet Message-IDs are skipped. Without a Message-ID, a fingerprint uses normalized subject, sender, To recipients, date, body, and attachment hashes.
- Existing messages are kept. Importing a more complete copy does not replace an existing partial copy.
- Completion reports new messages, duplicates, and file errors.
- Limits: 2 GB per uploaded file, 8 GB total or expanded data, and 60,000 files per import.

For Outlook-cache recovery and document text extraction, install the additional dependencies first:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-recovery.txt
```

On Windows, use `.venv\Scripts\python.exe` instead. The importer uses this virtual environment when it exists.

The Outlook snapshot should include `EBWebView/Default/IndexedDB`, plus `Attachments` and `Cache` where available. The `Microsoft.OutlookForWindows` package folder alone generally does not contain the message database. Operate on a copied snapshot; the app does not connect to Outlook or the mail server.

## Recipient accounts

The account selector derives views from **To** email addresses, such as `Alex Example <alex@example.test>`. A message addressed to several recipients appears in each matching account view. These are local recipient views, not authenticated mail accounts.

Search, folder counts, unread filtering, attachment browsing, and AI questions use the selected account. Cc/Bcc and outbound messages not addressed To that address are excluded. **All accounts** shows the complete imported archive and calendar records. Changing accounts starts a fresh chat.

## AI chat with VibeRouter

Click **AI Chat** in the top bar, or open http://127.0.0.1:8765/#chat.

The default connection is the VibeRouter macOS app’s local API at `http://127.0.0.1:8318/v1`. Start VibeRouter and connect a provider there first. The default model ID is `gpt-5.6-sol`; choose a model available in your own gateway.

**Change model** opens provider/model dropdowns from VibeRouter’s live catalog. Before saving, the app checks that the model exists and completes a real function-call round trip. A failed selection keeps the previous configuration. Catalog presence alone does not guarantee an active provider session.

Questions, recent conversation history, and retrieved passages go through VibeRouter to the selected provider. The entire archive is not uploaded. Local ranked keyword search covers message bodies, calendar records, and extracted document text. Read-only tools provide source passages and exact mail statistics; answers link back to sources. The chatbot cannot send, delete, or mark mail as read.

Model preferences are saved locally in `.archive-ai.json`; API keys remain in server memory. Environment overrides are `VIBEROUTER_BASE_URL`, `VIBEROUTER_MODEL`, and `VIBEROUTER_API_KEY`. No credentials belong in Git.

## Data and limitations

- `MailArchive/`: initial reconstructed archive, if one exists.
- `imports/<id>/work/MailArchive/`: successfully imported datasets.
- `imports/catalog.json`: committed import registry. Keep the complete imports directory with the app.
- `snapshot/` and `recovery/`: optional direct-extraction inputs and intermediates.

All these locations are ignored by Git. Duplicate-only imports discard their temporary working files. A server restart during an unfinished import requires selecting the source files again; committed imports survive restarts.

Cache-derived EML files are reconstructions, not original server MIME. Bodies may be normalized HTML; missing attachments, incomplete records, and cached image renditions are labelled. Uncached server-only mail cannot be recovered offline. Original read/unread state is retained; reading in this app does not change it.

PDF and Office document text can be indexed. Images and scans without text are not OCRed; audio and video are not transcribed. The AI retrieves selected evidence, not every message for every answer. Check citations before relying on a conclusion.

Message HTML is sanitized and sandboxed with remote content blocked. The server binds only to localhost and protects write/AI endpoints against cross-origin requests. Downloaded EML retains its cached HTML; other mail clients control their own remote-content behavior.

## Development and tests

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check viewer/app.js
```

Synthetic tests cover imports, deduplication, account scoping, attachment indexing, path validation, provider failures, and connection verification. Optional archive integrity tests run only when a local `MailArchive/index.json` exists. No private test dataset is required or distributed.

Direct recovery tools, for an existing snapshot under `snapshot/Olk/`:

```sh
.venv/bin/python scripts/decode_snapshot.py
.venv/bin/python scripts/export_mail.py
.venv/bin/python scripts/index_attachment_text.py
```

Run these sequentially and restart the viewer after rebuilding. The inspection helpers under `scripts/` are developer utilities for examining a local cache.

`python3 scripts/package_app.py` builds a local portable ZIP. **That ZIP includes local mail data if present** and must not be committed or published as a code release.

## Third-party code

The vendored [CCL Chromium Reader](https://github.com/cclgroupltd/ccl_chromium_reader) retains its MIT license in `vendor/ccl_chromium_reader/LICENSE`. Recovery also uses the dependencies declared by that package and `pypdf`. The runtime viewer and AI client use the Python standard library.
