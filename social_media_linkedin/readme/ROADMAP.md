Like the comments
-----------------

- To like a comment you need the scopes:

  * w_member_social_feed,
  * r_organization_social_feed
    Which are special permissions granted by LinkedIn, see the products of the
    [LinkedIn Marketing API](https://learn.microsoft.com/en-us/linkedin/marketing/getting-started)

Comments on publications
------------------------

- Images, videos, documents, or any type of media are not allowed
  in post comments via the API, due to LinkedIn's own limitations.
  Although there is an example of how to do it in the
  [Comments API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/comments-api),
  in practice it doesn't work, even in paid versions.

Post with video or image
------------------------

- The Posts API only supports creating a post with either images or a video,
  not both at the same time: the `content` of a post holds a single `media`
  entry. When a post carries a video, its images are ignored.

  https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-07&tabs=http#post-schema

Images removed from a publication
---------------------------------

- The statistics synchronization mirrors the medias of the posts that are
  still online: an image removed on LinkedIn leaves the publication in Odoo
  too. A post deleted on LinkedIn is not touched, it keeps its medias as
  history together with its *Deleted* state.
- The Posts API answers a post without media with an empty `content`, which
  is indistinguishable from a response that did not carry the content this
  time. The medias themselves are the ones of the
  [Images API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/images-api).
  An incomplete answer therefore drops the images of that publication.
  The ones downloaded from LinkedIn come back on the next synchronization,
  but a local copy attached at publishing time, kept because LinkedIn never
  exposed its media, cannot be downloaded again and is lost.

Video of a publication
----------------------

- The video of a published post is not attached to the publication itself:
  only the *has video* flag is kept, and the dashboard shows a camera icon.
  The video stays available on the post it was published from.

Video upload
------------

- LinkedIn decides how a video is split: `initializeUpload` answers one
  instruction per part, of 4 MiB each except the last one, and every part is
  uploaded with its own request. The identifiers LinkedIn returns for the
  parts are sent back to `finalizeUpload` in the same order, so the video is
  put together as it was cut. A 22 MB video takes 6 parts and around 25
  seconds, upload and processing included.

  https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api

- A post publishes a single video, so a post carrying several is refused
  before uploading anything: LinkedIn would only keep the first one and the
  others would be transferred and processed for nothing.
- Odoo does not check the size nor the duration of the video before uploading
  it: those limits are the ones of the
  [Videos API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api)
  and LinkedIn applies them while processing. A video out of limits is
  transferred whole and rejected afterwards, in the processing phase, with
  *LinkedIn could not process the video*.

Publishing options
------------------

- Every publication is created **public**, in the main feed, with no targeting
  by country, language or industry, and letting it be shared: `visibility`,
  `feedDistribution`, `targetEntities` and `thirdPartyDistributionChannels`
  are fixed in the code and cannot be configured from Odoo. Scheduling is not
  delegated to LinkedIn either: the Odoo scheduled action is the one that
  publishes when the date arrives.

  https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api

Rate limits
-----------

- The module does not handle the
  [throttle limits](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits)
  of LinkedIn, applied per day and per application. When LinkedIn answers with
  a limit error, the operation is recorded as failed like any other error and
  has to be retried later by hand; only a credential rejection triggers an
  automatic retry, and only once.
- Those limits are counted **per endpoint**, so what matters is not the total
  number of calls but how they spread. A full synchronization spends up to 50
  calls on `/rest/posts` alone, plus one per batch of identifiers on each of
  the statistics endpoints.
- The scheduled action checking for updates costs **two calls per account and
  run**, whatever the number of publications, one when it does find something,
  and none at all for an account already announcing updates or with no
  organization linked. It reads the figures LinkedIn reports for the whole page
  day by day and compares them against the ones the last import left: no
  publication is read one by one to decide whether the dashboard should
  announce updates. Running every two hours, that is around 24 calls a day per
  account.
- The **Update** button no longer walks the feed. The statistics are asked for
  by publication identifier, and those identifiers are already stored in Odoo,
  so one page of the feed is enough: the one sorted by last modification, which
  is what brings the publications created or edited on LinkedIn. That is one
  call instead of one per hundred publications.
- **Asking LinkedIn for only the publications that changed is not possible**
  with these endpoints, so the statistics still cost one call per batch of
  identifiers whatever moved:
    - The `/posts` finder takes `author`, `start`, `count`, `sortBy` and
      `viewContext`. There is no `since` of any kind, so there is no equivalent
      to what the X connector does with `since_id`.
    - The statistics of specific publications cannot be restricted to a period:
      *"Time-bound statistics is not supported for specific share queries"*.
    - The daily figures of the page say that something moved, not which
      publication moved.
- There **is** a stream of engagement events, and it is not used. It would tell
  which publication changed, and with it the refresh could ask about that one
  alone. It is not implemented because of three limits worth weighing first:
  it only reports reactions, comments and reshares, never impressions or
  clicks, which would still need the ordinary refresh; the publication it
  points at comes as an `urn:li:activity:` and only the webhook payload carries
  the matching `urn:li:share:`, the pull finder does not, so pulling alone
  cannot attribute an event to a publication; and the webhook needs a publicly
  reachable HTTPS URL validated by LinkedIn plus a subscription per member and
  organization. The permission it needs, `rw_organization_admin`, is already
  requested by this module.

  https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-social-action-notifications

Synchronization scope
---------------------

- **Only the full resync notices a publication deleted on LinkedIn.** The
  ordinary refresh cannot: it does not read the whole feed any more, so a
  publication missing from what it read says nothing. The *Full resync* button
  of the account does it on demand, and a scheduled action does it weekly on
  its own, so the *Deleted on LinkedIn* ribbon may take up to a week to appear.
- The full resync is also the expensive pass, one call per hundred publications
  of every account, and every account runs in the same weekly run. On a
  database with several large pages that run alone could exhaust the daily
  quota and make the manual refresh fail with it. Spreading the accounts over
  the days of the week is the way out and is not implemented.
- The synchronization walks the feed of the organization page by page
  (`count=100`) up to **50 pages**, that is 5000 publications. A page is only
  taken as the last one when it comes back empty, because LinkedIn documents
  that a page may carry fewer publications than asked while more are left.
  On an account whose feed is longer than that, the answer is incomplete and
  the sweep that marks as *Deleted* what is no longer on LinkedIn is skipped
  for that run: reporting nothing is preferable to marking a publication
  that is still online.
- The statistics of the publications are asked in as many calls as the 4 KB
  limit of the query string needs, since those endpoints take every identifier
  in the URL and none of them paginates. Around a hundred publications fit in
  one call, so a full feed takes several.

  https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/share-statistics
- The check for updates only tells that *something* on the page moved, not
  which publication moved. It does not need to: the only thing it decides is
  whether the dashboard shows the notice inviting to synchronize. A change
  that cancels itself out between two runs, a reaction removed and another
  one added, leaves the figures of the page where they were and goes
  unnoticed until the next synchronization.
- The check watches the **daily** figures of the page, over a window of the
  last seven days, and not the lifetime totals the same endpoint answers when
  no time interval is given. Those lifetime totals lag behind: measured against
  a real account, a reaction was already counted in the daily buckets while the
  lifetime figures still ignored it an hour and a half later, and the sum of
  the twelve monthly buckets matched the lifetime answer on every figure except
  that one reaction. Two consequences worth knowing:
  - Activity older than the seven-day window is not announced. It is imported
    all the same when the user synchronizes, because the import reads the
    publications themselves and not this window.
  - Impressions reach the daily buckets later than reactions do, so a
    publication that only gained views may be announced a run or two later
    than one that gained a reaction.
- The engagement is not compared. It is a ratio of the clicks, reactions,
  comments and shares over the impressions, so it cannot move without one of
  those moving, and it is the only non-integer figure of the set.
- The statistics endpoint only answers activity of the **last 12 months**, on a
  rolling window. A publication older than that stops being counted, which can
  move the figures of the page on its own, with nobody having interacted with
  anything. The check announces updates once when that happens and the next
  import reconciles it.

Video processing
----------------

- LinkedIn processes an uploaded video before it can be published, so
  publishing a post with a video waits until the video is available. The wait
  can be tuned with the `social_media_linkedin.video_poll_attempts` and
  `social_media_linkedin.video_poll_delay` system parameters (30 attempts
  every 2 seconds by default). A long video may need more than that.
