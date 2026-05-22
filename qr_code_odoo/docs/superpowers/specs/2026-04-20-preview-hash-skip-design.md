# Preview Hash-Skip Optimization — Design

**Date:** 2026-04-20
**Scope:** `qr_code_odoo` addon — `/vcard/preview` endpoint shared by `/get-started` and `/bulk-onboard`.

## Problem

Every keystroke in either onboarding form triggers `POST /vcard/preview` →
`generate_preview()` (`controllers/main.py:1329`). The slow path always runs:

1. Write/create the preview `partner.vcard` row.
2. Unlink + recreate child `partner.vcard.website` and `partner.vcard.videos` rows.
3. Call `action_generate_website_page()` (`models/partner.py:3228`), which:
   - Builds the full QWeb template via `_build_dynamic_template()` (~700 lines of
     string assembly, `models/partner.py:3411`).
   - Writes the result to `ir.ui.view.arch_db` unconditionally.
   - Calls **site-wide** `ir.ui.view.clear_caches()` and `ir.qweb.clear_caches()`
     unconditionally (`models/partner.py:3259-3260`) — this invalidates compiled
     views for **every** page on the site, slowing concurrent visitors on each
     keystroke.
4. Commits the cursor up to three times (`controllers/main.py:1576, 1588, 1606`).

Even when the form data has not changed (e.g., user clicks back into the field
and tabs out), the entire pipeline re-runs.

## Goal

Short-circuit the endpoint to a single SELECT + return when the inputs that
produced the current rendered preview are unchanged. Keep correctness intact for
every input that affects rendered output. Eliminate site-wide cache thrash on
no-op preview updates.

## Non-goals

- Touching the slow-path's transaction semantics beyond collapsing duplicate
  commits.
- Refactoring `_build_dynamic_template` itself.
- Replacing the existing `partner.vcard` retry loop for `SerializationFailure`.
- Adding test infrastructure where none exists for this controller.

## Architecture

### New stored field

`preview_template_hash = fields.Char(default=False, copy=False)` on
`partner.vcard`. Holds a sha256 hex digest of the inputs that produced the
current `arch_db` for this preview. Stored so the cache survives server restarts
and works uniformly across workers.

### Controller flow (revised `generate_preview`)

1. Parse `data` — unchanged.
2. Lookup preview vCard by slug `preview-{user.id}` — unchanged.
3. **Resolve image identities without DB writes:**
   - `image_token = sha256(data['image_base64'])[:16]` if provided, else
     literal `'DEFAULT'`.
   - Same for banner.
4. **Resolve mailing list and leadback channel codes** to a stable form
   (mailing-list name string, sorted list of channel codes). The existing slow
   path will resolve these to ids; the hash uses the codes/names so we don't
   need a DB read on the fast path.
5. **Compute** `incoming_hash = _compute_preview_hash(data, channel_codes,
   websites, videos, image_token, banner_token)`.
6. **Fast path:** if `preview_vcard` exists AND
   `preview_vcard.preview_template_hash == incoming_hash`:
   - SELECT `website.page` by `url='/preview-{user.id}'`, limit 1.
   - If found → return `{success: True, preview_url, vcard_id,
     website_page_id}`. No commit (pure read).
   - If not found → fall through to slow path (handles out-of-band deletion).
7. **Slow path:** existing write/create + retry loop + child-record churn +
   `action_generate_website_page()`, plus:
   - Set `vcard.preview_template_hash = incoming_hash` in the same write.
   - Single `cr.commit()` at the end. Both the "page not found → regenerate
     again" recovery branch (`controllers/main.py:1583-1593`) and the "page not
     published → republish" branch (`controllers/main.py:1603-1606`) are
     removed; `action_generate_website_page()` already creates the page with
     `is_published=True` on first run, so these branches are dead in practice
     once the duplicate-commit pattern is gone.

### Tier-A cleanup inside `action_generate_website_page`

In the `existing_view` branch (`models/partner.py:3252-3262`), wrap the
`arch_db` write and the two `clear_caches()` calls in:

```python
if existing_view.arch_db != template:
    existing_view.write({'arch_db': template})
    self.env['ir.ui.view'].clear_caches()
    self.env['ir.qweb'].clear_caches()
```

This protects the site-wide cache on the rare slow-path runs where the
rendered template is byte-identical (e.g., user toggled a flag back and forth
across two preview calls).

## Hash inputs (canonical contract)

Every input the renderer reads must appear here. Missing one = stale preview.

**Scalars** (every key currently written to `vals` in `generate_preview`):
`name, company_name, street, street2, city, zip, function, phone, mobile,
email, website, calendly_url, about, primary_color, secondary_color,
website_template, whatsapp_url, linkedin_url, linkedin_url_company, youtube_url,
facebook_url, facebook_url_company, lead_button_label, form_thank_you_message,
show_form, notify_on_new_lead, intro_email_enabled, enable_instant_leadback,
leadback_send_email, leadback_enable_messaging, show_reviews`.

**Resolved associations:**
- `effective_show_form` — the **post-override** boolean: if `data.show_form`
  is truthy but `mailing_list_name` is empty/whitespace, the slow path
  silently sets `show_form=False` (`controllers/main.py:1410-1413`); the hash
  must reflect that override or two semantically-identical previews will
  hash differently. Use this in place of the raw `show_form` scalar.
- `mailing_list_name` — the stripped string, included only when
  `effective_show_form` is `True`; otherwise `''`. We do not include the
  resolved id because the id may change across rebuilds without the
  rendered template changing.
- `leadback_channel_codes` — sorted list of code strings (the form sends
  codes; the slow path resolves them to ids via DB lookup, but the hash
  uses the codes directly so the fast path needs no DB read).

**Child collections (order matters):**
- `websites = [(url, name, color), ...]` from `website_url[]`,
  `website_name[]`, `website_color[]`.
- `videos = [(url, name), ...]` from `video_url[]`, `video_name[]`.

**Image identity:**
- `image_token` and `banner_token` as defined above (`sha256(base64)[:16]` or
  `'DEFAULT'`).

**Canonicalization:**

```python
payload = {
    'scalars': {k: data.get(k, '') for k in HASHED_SCALARS if k != 'show_form'},
    'effective_show_form': effective_show_form,
    'mailing_list_name': mailing_list_name if effective_show_form else '',
    'leadback_channel_codes': sorted(channel_codes),
    'websites': websites,
    'videos': videos,
    'image_token': image_token,
    'banner_token': banner_token,
}
canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

`HASHED_SCALARS` is defined as a module-level tuple in `controllers/main.py`
adjacent to the helper, so any future addition to `vals` is one edit away from
being hash-aware.

## Error handling

- Fast-path `website.page` lookup returns `None` → log info, fall through to
  slow path. Hash is recomputed and rewritten on success.
- `_compute_preview_hash` raises → log warning with stack trace, fall through
  to slow path. Correctness over speed.
- Slow path failure handling is unchanged (existing `SerializationFailure`
  retry loop and exception logging stand).

## Files changed

- `models/partner.py`
  - Add `preview_template_hash` field (~1 line near other vcard fields).
  - Wrap `existing_view.write` + `clear_caches()` calls in an
    `if arch_db != template:` guard (~5 lines).
- `controllers/main.py`
  - Add module-level `HASHED_SCALARS` tuple and `_compute_preview_hash` helper
    (~25 lines).
  - Insert fast-path branch after preview vCard lookup (~15 lines).
  - On slow path: include `preview_template_hash` in the `vals` write; collapse
    the three `cr.commit()` calls to one; remove the redundant "page not found
    → regenerate" branch.

No XML changes. Module upgrade still required for the new field.

## Manual test plan

1. **Same-input dedup.** Open `/get-started`, type a name. First request slow
   (current latency). Trigger the same payload (e.g., click outside and back
   in) → fast path hits, response < 50ms server-side. Verify in Odoo log.
2. **Single-field invalidation.** Change one form field → slow path runs
   exactly once, then subsequent identical payloads fast.
3. **Toggle round-trip.** Toggle `show_form` on then off → second call hits
   fast path; verify the new `if arch_db != template:` guard skips the
   cache clear in the slow path that runs in between (look for absence of
   `clear_caches` log or instrument with a log line during dev).
4. **Restart persistence.** Hit `/get-started` once, restart the Odoo
   service, re-open `/get-started` without changes → fast path hits on
   first preview request because `preview_template_hash` is stored.
5. **Endpoint sharing.** Repeat 1–2 on `/bulk-onboard` — same behavior since
   both forms POST to `/vcard/preview`.
6. **Cache thrash regression check.** Open a public page in another browser
   tab, type in the preview form, refresh the public page after every few
   keystrokes. Latency should stay flat (no per-keystroke cache invalidation
   anymore).

## Risks

- **Missed input.** If a future template change adds a new vcard field that
  affects rendering and the hash is not updated, previews will stale-cache
  until something else in the hash changes. Mitigation: `HASHED_SCALARS` is
  a single visible tuple at the top of the controller; any developer
  adding a `vals` key sees it immediately.
- **Image identity collision.** A truncated 16-char sha256 prefix has
  ~2^-64 collision probability for randomly-generated content; for image
  bytes, effectively zero. Acceptable for a preview cache.
- **Schema migration.** Adding the field requires `-u qr_code_odoo`. This
  is already required for the unrelated XML changes shipped earlier this
  session, so no incremental cost.
