This module provides the fundamental foundation for social media management.
It facilitates the integration of user accounts, posts, reactions (likes),
comments, and graph-based analysis. Designed to be flexible and scalable,
it allows developers and businesses to integrate and customize social features
according to their needs.

This module does not connect to any social media by itself: it brings the
models, the security, the scheduled actions and the common interface. To use
it, a connector module has to be installed as well (for instance
*Social Media Linkedin* or *Social Media X*), which is what registers the
social media, implements the OAuth authorization and publishes for real.

Main features:

- Integration of multiple user accounts.
- Basic methods that can be extended and adapted to suit the social media.
- Basic business structure.
- Dashboard of published posts with video and deletion indicators.
- A *Campaigns* menu inside the application, so the Odoo marketing campaigns
  (`utm.campaign`) can be managed without installing another marketing
  application. A post carries the campaign it belongs to, and the campaign
  form opens a new post already attached to it.
- Campaign badge on the posts kanban and on the dashboard cards.
- The posts of a marketing campaign, shown on the campaign from the moment
  they are drafted, with their consolidated figures and a stat button on the
  campaign form, the same way *Email Marketing* and *SMS Marketing* plug into
  a campaign.
- A UTM medium per social media and a UTM source per publication, so the
  links of a post are tracked separately for each account it is published on.
- Links of a published message routed through the Odoo link tracker, so a
  click from the social media is counted in Odoo and attributed to the
  campaign and to the publication.
- Because of the above the module depends on `utm` and on `link_tracker`,
  which are installed with it. They are core modules that bring the marketing
  campaigns, the mediums, the sources and the short links, and they change
  nothing in the social media data.
- Initial synchronization of the posts and their statistics right after an
  account is linked; a monthly cron picks up the accounts that are still
  waiting for it, and afterwards they are refreshed on demand from the
  dashboard.
- Account credentials (OAuth tokens) are only visible to administrator users.
