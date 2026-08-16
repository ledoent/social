This module provides the necessary functionality for
basic interaction with the LinkedIn social media.

Main features:
- Integration of the LinkedIn company pages (organizations) the user
  administrates; personal profiles are not supported.
- Post creation, with images or a video: LinkedIn publishes either the images
  or the video, never both.
- Post reactions (likes, comments).
- Full resync of a page, which reads the whole feed and reports the
  publications deleted on LinkedIn.
- Reports and graphs with agnostic metrics.

Liking a comment is not available: LinkedIn grants the scopes it needs
only as special permissions, see the roadmap.


Statistics account
-------------------
1. The eye icon: Total number of views, which may include multiple views by the same user.
2. The hand icon: means the interactions (clicks, likes, comments and shares)
   accumulated by the posts created historically on the account.
3. The star icon: the engagement of the publications. LinkedIn reports an
   engagement rate for each publication, and the account adds them up, so the
   figure is a sum of rates and not a percentage of the account.

   ![STATISTICS_ACCOUNT](../static/img/readme/STATISTICS_ACCOUNT.png)
