Connect a social account
---------------

- Go to *Social Media* > *Configuration* > *Social Media*, click the
  platform card (LinkedIn, Facebook, …).
- The wizard opens on the **pre-flight scene** — branded introduction
  band with the platform color, a one-line headline, a time estimate,
  and a two-column scope disclosure ("We'll do" / "We won't touch").
  Decide whether you have a developer app already; if not, click
  *Show me how to make one* to open the platform's dev portal in a
  new tab. The wizard state is preserved while you do that.
- Click *I have an app →* to advance to the credentials step. Channel
  modules (`social_media_linkedin`, `social_media_facebook`) populate
  the required fields there.

Connection health board
---------------

- *Social Media* > *Configuration* > *Social Accounts* opens the
  status-board kanban. Each card shows the platform brand band, the
  account name + URL, the current **health pill** (Healthy / Warning /
  Rate limited / Expired / Disconnected / Never connected), follower
  count + 7-day delta arrow, the last published post timestamp, and
  three actions: *Reconnect*, *Test post* (enabled only when the
  account is Healthy), and *Disconnect*.
- Cards sort by `health_severity` descending so degraded accounts
  surface at the top.
- The search view ships with two one-click filters: *Degraded* (any
  non-healthy state) and *Healthy*. Group by *Platform* or *Status*
  for triage across many accounts.

Daily health refresh
---------------

- The `Social: refresh account health` scheduled action (daily, 06:00
  UTC by default) iterates every active `social.account` and calls
  the channel module's `_refresh_account_health()` to update the
  follower count + health status.
- A follower-count snapshot is appended to
  `social.account.follower_history` (a JSON column capped at 90
  entries / ~3 months). Same-day re-runs overwrite the latest entry
  rather than duplicating.
- On any transition into a degraded state (Warning, Rate limited,
  Expired, Disconnected), the cron calls `_post_health_warning()` —
  default behavior schedules a "Reconnect *<platform>*"
  `mail.activity` todo on the user who connected the account. Stale
  activities from previous degradations are removed so the activity
  list never accumulates duplicates across recover-then-degrade
  cycles.
- Schedule and cadence are editable: *Settings* > *Technical* >
  *Scheduled Actions* > *Social: refresh account health*.

Generate group campaign.
---------------

- Go to *Social Media* > Campaign group > New
- Fill in the required fields
  ![CREATE_GROUP_CAMPAIGN](/social_media_base/static/img/readme/CREATE_GROUP_CAMPAIGN.png)
- Save

Generate campaign.
---------------

- Go to *Social Media* > Campaign > New
- Fill in the required fields
  ![CREATE_CAMPAIGN](/social_media_base/static/img/readme/CREATE_CAMPAIGN.png)
- Save
