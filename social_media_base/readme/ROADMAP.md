Planned improvements that are *not* in this module yet but are on the
roadmap of the broader social-media consumer-grade onboarding effort.

Connect wizard (Scene 2-4)
---------------

- **Smart credential entry** — live format validation on Client ID /
  Client Secret as the user types; mask-by-default with one-click
  reveal; a *Test these credentials* button that does an
  unauthenticated OAuth probe and reports "These look valid" /
  "Platform doesn't recognize this Client ID" before commit.
- **Branded loader during OAuth redirect** — replace the blank "Opening
  LinkedIn…" gap with a branded loading state, then a scope-specific
  recovery message if the user grants the wrong scopes on the platform
  side ("We didn't get `w_organization_social` — try again?").
- **Success card with live data** — after a successful connect, show
  the actual entity (avatar, follower count, sample of recent posts)
  pulled live, plus a *Send test post* button that publishes + deletes
  to prove the wiring works end-to-end.

Status board (Tier 2 follow-ups)
---------------

- **Sparkline trend** in each kanban card driven from
  `follower_history` (visualise the JSON column).
- **Per-error-code recovery copy** on failed `social.post` — surface
  "Token revoked, click to reconnect" instead of generic 401 messages.
- **Configurable delta windows** on `social.account.follower_count_delta_*`
  (7d/30d hard-coded today; let admins pick).

Channel modules
---------------

- LinkedIn and Facebook channel implementations of
  `_refresh_account_health()` and `_test_post_and_delete()` ship in
  `social_media_linkedin` and `social_media_facebook` respectively
  (separate PRs).

Performance
---------------

- `_compute_last_post` filters all `post_account_ids` in Python; for
  accounts with thousands of historical posts this should be
  rewritten as a `search(..., limit=1, order='published_date desc')`
  query.
