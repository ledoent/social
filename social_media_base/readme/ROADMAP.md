Multi-company scope of the posts.
---------------

Only the accounts (`social.account`) are multi-company: they carry a company
and a record rule that filters them. The posts and their publications have
neither a company field nor an equivalent rule, so they are only filtered by
their responsible user. In a multi-company database a social media
administrator therefore sees the posts of every company.

Liking and replying to a comment are unfinished.
---------------

Neither action is reachable from the interface, and the server side of both is
a stub. Nothing is broken today, but the whole chain has to be finished or
removed as a unit, never half of it:

- The *Recommend* span of `SocialComment` is guarded by
  `t-if="... in this.mediaNotLikeEnable()"`. OWL emits `in` as the JavaScript
  operator, and the helper returns an array, so the test looks up an index and
  is always false: the span never reaches the DOM. Replacing `in` with
  `.includes()` alone is not the fix, because the helper lists the medias where
  liking is *not* available and LinkedIn adds itself to it.
- `action_like_comment` answers `success: True` with an empty message on
  `social.post.account` and `success: False` with an empty message on LinkedIn,
  so showing the button would either raise a rainbow man for a like that never
  happened or notify an empty text.
- The *Comment* span carries a literal `d-none` class, and `onReplyComment()`
  only triggers a reload: it never calls `_onReplyComment()`, the hook meant to
  build the reply, which no connector overrides.
