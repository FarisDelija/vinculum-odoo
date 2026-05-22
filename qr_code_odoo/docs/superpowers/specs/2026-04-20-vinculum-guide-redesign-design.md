# /vinculum/guide Redesign — Design

**Date:** 2026-04-20
**Scope:** `qr_code_odoo` — replace the current single-page `/vinculum/guide`
template with a hub + sub-page IA that justifies the platform's price point
and serves both end users and administrators.

## Problem

The current `/vinculum/guide` page (`views/vinculum_guide_template.xml`,
572 lines) tries to be three things at once: marketing explainer, setup
tutorial, and operational reference. It uses 2018-era Bootstrap card patterns
(coloured-header cards, 3-up icon grids, badge step lists, "Pro Tip" alerts),
which reads generic and does not match the production polish of a $399 product.
Both end users and admins click "How to Use Vinc" from the in-product dashboard
and the vCard form view; both come away with the same uniform marketing-ish
content rather than answers to their actual job-to-be-done.

## Goal

Replace the single page with an architecture that:

- Splits content by audience (User / Admin) instead of mixing both.
- Has a polished landing page (the hub at `/vinculum/guide`) plus 8 dedicated
  sub-pages that can each go deep on one topic.
- Provides a shared visual shell so adding the 9th, 10th, etc. page later
  costs only content, not layout work.
- Ships with shippable copy (per user choice (M)): I draft all 8 sub-pages
  in a "v1 voice", with explicit `[NEEDS YOUR INPUT]` and `<!-- NEEDS
  SCREENSHOT -->` markers wherever product-judgment or imagery is required.

## Non-goals

- Building a docs-site infrastructure with persistent left nav across the
  whole `qr_code_odoo` addon (that was option (γ); we picked the
  hub+sub-pages middle ground).
- Migrating existing copy verbatim — most of the current text is being
  rewritten or dropped.
- Internationalization — strings stay in English; translation hooks added if
  Odoo's `t-translation` is already in use elsewhere in the file (it is, so
  we keep using `_t()` style markup where appropriate).
- Backend admin pages for editing the guide content (it stays as QWeb
  templates, like today).

## Architecture

### URL scheme

```
/vinculum/guide                    → hub
/vinculum/guide/setup-card         → user track
/vinculum/guide/share-card         → user track
/vinculum/guide/lead-capture       → user track
/vinculum/guide/reviews            → user track
/vinculum/guide/bulk-onboard       → admin track
/vinculum/guide/crm                → admin track
/vinculum/guide/nfc                → admin track
/vinculum/guide/automations        → admin track
```

Routes are flat (no `/users/` or `/admins/` namespace) so URLs stay short and
the in-product "How to Use Vinc" buttons can deep-link without growing.

### Controller

In `controllers/main.py`, replace the existing `vinculum_guide` method with:

```python
import werkzeug

GUIDE_TOPICS = {
    'setup-card':   ('qr_code_odoo.vinculum_guide_setup_card',   'users'),
    'share-card':   ('qr_code_odoo.vinculum_guide_share_card',   'users'),
    'lead-capture': ('qr_code_odoo.vinculum_guide_lead_capture', 'users'),
    'reviews':      ('qr_code_odoo.vinculum_guide_reviews',      'users'),
    'bulk-onboard': ('qr_code_odoo.vinculum_guide_bulk_onboard', 'admins'),
    'crm':          ('qr_code_odoo.vinculum_guide_crm',          'admins'),
    'nfc':          ('qr_code_odoo.vinculum_guide_nfc',          'admins'),
    'automations':  ('qr_code_odoo.vinculum_guide_automations',  'admins'),
}

@http.route('/vinculum/guide', type='http', auth='public', website=True)
def vinculum_guide_hub(self):
    return request.render('qr_code_odoo.vinculum_guide_hub',
                          {'current_topic': None, 'current_track': None,
                           'guide_topics': GUIDE_TOPICS})

@http.route('/vinculum/guide/<string:topic>', type='http', auth='public',
            website=True)
def vinculum_guide_topic(self, topic):
    if topic not in GUIDE_TOPICS:
        raise werkzeug.exceptions.NotFound()
    template, track = GUIDE_TOPICS[topic]
    return request.render(template,
                          {'current_topic': topic, 'current_track': track,
                           'guide_topics': GUIDE_TOPICS})
```

The existing `action_open_vinculum_guide` callers in `models/partner.py:1492`
and `models/user_dashboard.py:236` already point at `/vinculum/guide` — no
change needed there.

### Templates

Three XML files, replacing the existing one and adding two:

- `views/vinculum_guide_template.xml` — REPLACE (~150 lines). Holds:
  - `vinculum_guide_layout` — shared shell template with sidebar + content
    slot + footer, `t-call`'d by every page.
  - `vinculum_guide_hub` — landing page at `/vinculum/guide`.
- `views/vinculum_guide_users.xml` — NEW (~400 lines). Four user-track
  sub-page templates, each `t-call`-ing `vinculum_guide_layout`.
- `views/vinculum_guide_admins.xml` — NEW (~450 lines). Four admin-track
  sub-page templates, same pattern.

Splitting by track keeps each file under ~500 lines and matches how a
product/content team would own the work — User Success owns the user pages,
Admin/IT owns the admin pages.

### Manifest

In `__manifest__.py`'s `data` list, the existing line
`'views/vinculum_guide_template.xml'` stays (file is replaced, key unchanged).
Add:

```python
'views/vinculum_guide_users.xml',
'views/vinculum_guide_admins.xml',
```

After the existing `vinculum_guide_template.xml` entry so the layout template
loads first.

## Shared layout component

`vinculum_guide_layout` provides a consistent shell. Sub-page templates use:

```xml
<template id="vinculum_guide_setup_card" name="Setting Up Your Card">
  <t t-call="qr_code_odoo.vinculum_guide_layout">
    <t t-set="page_title">Setting Up Your Card</t>
    <t t-set="page_summary">From a fresh install to a published vCard in
      under five minutes.</t>
    <t t-set="content">
      <!-- page-specific HTML here -->
    </t>
  </t>
</template>
```

The layout reads `current_topic`, `current_track`, and `guide_topics` from
the controller context and `page_title`, `page_summary`, `content` from the
caller's `<t t-set>` blocks.

**Layout slots:**

- **Top bar** — Vinc wordmark on the left; on the right, "← Back to Vinc"
  link to `/odoo` (Odoo 17 backend root) for authenticated users, and to
  `/web/login` otherwise. Detect via `request.session.uid`.
- **Left sidebar** — sticky, ~260px wide on ≥md, collapses to a top
  hamburger on small screens. Two collapsible groups: "For Users" and
  "For Administrators". Each group lists the four sub-pages of its track
  with a single Lucide-style icon and the title. The current page is
  highlighted via comparison with `current_topic`. The hub (`/vinculum/guide`)
  shows as the section header and is itself a link.
- **Main content** — page header (breadcrumb, H1 from `page_title`,
  summary from `page_summary`), a TOC injected only when the page sets
  `<t t-set="show_toc">true</t>` (4+ H2s rule), then `t-out="content"`.
- **Next/Previous nav** at the bottom, computed from the order of
  `guide_topics` within the current track.
- **Footer** — "Was this helpful? 👍 👎" (mailto: links to support address
  for v1, no analytics endpoint), plus "Need more? support@getvinc.com" and
  "Report a doc issue → [`[NEEDS YOUR INPUT]: GitHub issues URL`]".

## Hub page anatomy

`vinculum_guide_hub` is the marketing-grade landing page that justifies the
investment. Sections, top to bottom:

1. **Hero** — one positioning sentence ("Vinc turns every team member into a
   lead-generating channel"), a one-line subheading, and a single primary
   CTA chosen by this rule:
   - Signed-in user **with at least one vCard** → "Open dashboard" → `/odoo`.
   - Signed-in user **with no vCard yet** → "Create your card" → `/get-started`.
   - Anonymous → "Create your card" → `/get-started` (the get-started flow
     itself handles the auth gate).

   Detection: `request.session.uid` truthy, plus a quick search using the
   same convention as `user.dashboard._compute_vcards`
   (`models/user_dashboard.py:64`) — match by `create_uid` and (if the
   request user has a partner email) by email. `partner.vcard` does not
   have a direct `user_id` field, so reuse that helper instead of inventing
   a new lookup. The count is cheap and only runs on the hub.
2. **Two-track picker** — two large side-by-side cards: "I'm setting up my
   card" → `/vinculum/guide/setup-card`; "I'm administering Vinc for my
   team" → `/vinculum/guide/bulk-onboard`. Each card has a one-line value
   prop and an icon. This is where the audience split is made obvious.
3. **What's inside, by track** — two columns mirroring the sidebar nav.
   Each column lists its four sub-page titles plus a one-line teaser per
   page (drawn from `page_summary` for each).
4. **Mental model** — three short paragraphs covering "How Vinc works
   end-to-end": create → distribute (QR/NFC/URL) → capture (form/reviews) →
   route (CRM/email). Replaces the bullet wall in the old page.
5. **Footer** — from layout.

Hub fits comfortably above the fold + one scroll on a 1440×900 display.
Punchy. No bullet walls.

## Sub-page anatomy

Common pattern for all 8 sub-pages:

- **Page header** (rendered by layout): breadcrumb (`Guide / For Users /
  Setup Your Card`), H1, one-sentence summary.
- **TOC** — only when 4+ H2s are present.
- **Body** — 3–6 H2 sections per page. Each H2 follows: short prose para →
  screenshot or numbered steps → optional "Notes" callout.
- **Next/Previous nav** — within track, from layout.

## Per-page content scope

| Page | Sections | Marked-for-input items |
|---|---|---|
| `setup-card` | Pick a slug · Add your photo & branding · Fill contact details · Choose a template · Publish | Form screenshot, brand voice tightening |
| `share-card` | QR code (download/print) · NFC (link to NFC sub-page) · URL/email signature · Adding to existing email signatures | Email-signature screenshot examples |
| `lead-capture` | Enable the form · Tag leads · Pick a mailing list · Customize the CTA + thank-you · How leads land in CRM | Mailing-list screenshots, exact CRM landing flow |
| `reviews` | Enable reviews on your card · Moderation flow · Where reviews show up | Whether reviews need approval (verify in code) |
| `bulk-onboard` | CSV format · Upload flow · Activation emails · Troubleshooting common rows | Real CSV example, max-row limit confirmation |
| `crm` | How vCard leads map to crm.lead · Lead routing rules · Pipeline integration · Lead tags | Default pipeline stage, role-based routing |
| `nfc` | Recommended cards · Programming via NFC Tools · Direct-write vs URL-write · Testing | Brand of cards you sell/recommend |
| `automations` | Intro email · Leadback (delay/channels) · Digest emails · Editing templates | Cadence defaults (read code), template editor screenshots |

I draft all 8 in a "v1 voice" matching the dashboard's friendly-but-direct
tone. Concrete labels, field names, and flow steps come from reading the
codebase. Items I cannot or should not invent are tagged inline:

- `[NEEDS YOUR INPUT]: <what to fill in>` for product-judgment items.
- `<!-- NEEDS SCREENSHOT: <description> -->` for imagery (HTML comment so it
  doesn't render but is greppable).

## Visual direction

Visual direction (palette, typography, component styling, hero treatment,
sidebar styling, illustration vs photography choices) is intentionally **not
locked** in this spec. It will be picked up by the `frontend-design` skill
in the implementation phase, which will surface 2-3 aesthetic directions
for the user to choose from before any HTML/CSS is written. The constraints
this spec hands to that phase:

- Must coexist with the existing in-product Vinc aesthetic on the
  `user.dashboard` view (gradient banners, 16px rounded corners, soft
  shadows, blue primary). Visitors will hop between the two — they need to
  feel like the same product.
- Must read as quality at first glance: a buyer judging the product within
  10 seconds should not see a 2018-Bootstrap-startup-guide page.
- Must work on mobile (sidebar collapses, content reflows). Many visitors
  will land here on a phone after scanning a vCard's QR.

## Error handling

- Unknown topic in URL → `werkzeug.exceptions.NotFound()` (Odoo renders the
  standard website 404, which inherits the website layout — acceptable).
- Layout's auth detection (for top bar CTA) tolerates `request.session.uid`
  being None or zero by defaulting to the unauthenticated CTA.
- TOC is omitted if `show_toc` is unset, regardless of H2 count, so
  per-page authors stay in control.

## Files changed

**Replaced:**
- `views/vinculum_guide_template.xml` — old 572-line single page out;
  ~150 lines containing layout + hub in.

**New:**
- `views/vinculum_guide_users.xml` — 4 user-track sub-pages.
- `views/vinculum_guide_admins.xml` — 4 admin-track sub-pages.

**Edited:**
- `controllers/main.py` — replace single route with hub + parametric route;
  add `GUIDE_TOPICS` constant; add `werkzeug` import if missing.
- `__manifest__.py` — add the two new XML files to `data`.

No model changes. No JS changes. No DB migration. Module upgrade still
required (XML changes).

## Manual test plan

1. **Hub renders:** `GET /vinculum/guide` → 200, hero + two-track picker
   visible, sidebar nav present.
2. **All 8 sub-pages render:** for each topic in `GUIDE_TOPICS`,
   `GET /vinculum/guide/<topic>` → 200, correct H1, sidebar shows correct
   highlight.
3. **Unknown topic 404s:** `GET /vinculum/guide/does-not-exist` → 404
   (standard Odoo website 404 page).
4. **Backend buttons still work:** "How to Use Vinc" buttons on dashboard
   and vCard form view both navigate to `/vinculum/guide`.
5. **Auth-aware top-bar CTA:** logged in → "← Back to Vinc" goes to `/odoo`;
   logged out → goes to `/web/login`.
6. **Mobile responsive:** sidebar collapses to a hamburger menu at <md
   breakpoint; content reflows; no horizontal scroll.
7. **Visual continuity:** open `/odoo/dashboard` then `/vinculum/guide` in
   the same session — does not feel like two different products.

## Risks

- **Content drift.** Per-page copy I draft against the current codebase will
  drift as features change. Mitigation: each page has a clear ownership
  marker at the top (in an HTML comment) naming which model/controller it
  documents, so a future developer touching that code knows where to
  update.
- **Sidebar grows.** v1 has 8 sub-pages. If the team adds 8 more, the
  sidebar gets unwieldy. Mitigation: deferred to that point — easy to add
  group headings or collapse-by-default.
- **Visual scope creep into this brainstorm.** The frontend-design skill
  will surface multiple visual directions. Risk that none feel right and
  the conversation re-opens IA decisions. Mitigation: this spec is the
  contract; visual direction is layered on top, not a redesign trigger.
