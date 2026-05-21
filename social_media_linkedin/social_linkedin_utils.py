# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

_URL_LINKEDIN = "https://www.linkedin.com/campaignmanager/accounts/"
_URL_REST_LINKEDIN = "https://api.linkedin.com/rest"
_URL_V2_LINKEDIN = "https://api.linkedin.com/v2"
_URL_AUTH_V2_LINKEDIN = "https://www.linkedin.com/oauth/v2"

_VERSION_STRING = "202502"

_HEADERS_LINKEDIN = {
    "X-Restli-Protocol-Version": "2.0.0",
    "LinkedIn-Version": _VERSION_STRING,
}

# Default OAuth scopes requested when none is configured on the
# social.account. The five entries below cover what the OCA module
# itself actually exercises (org-page posting + reads). LinkedIn's
# OAuth endpoint rejects the entire authorization request if the
# app on the dev portal doesn't have a Product approved for any
# requested scope — so we keep the default narrow and let admins
# opt into more via the per-account `linkedin_scopes` field once
# their app has the matching Product (Marketing Developer Platform,
# Advertising API, Sign In with LinkedIn, etc.).
_SCOPE_LINKEDIN_DEFAULT = [
    # Sign In with LinkedIn (default product, always available)
    "profile",
    "email",
    # Marketing Developer Platform (org-page posting + reads)
    "r_organization_social",
    "w_organization_social",
    "r_organization_admin",
]

# All scopes the module knows how to use, for the help-text on the
# wizard. Adding any of these to the per-account `linkedin_scopes`
# requires the corresponding LinkedIn Product to be approved on the
# dev app — otherwise OAuth fails with "Bummer, something went wrong".
_SCOPE_LINKEDIN_KNOWN = _SCOPE_LINKEDIN_DEFAULT + [
    # Advertising API (only needed if Ads features are used)
    "r_ads",
    "rw_ads",
    "r_ads_reporting",
    # Marketing Developer Platform (extended)
    "rw_organization_admin",
    "w_member_social",
    # Legacy / restricted (older apps may still have these)
    "r_basicprofile",
    "r_1st_connections_size",
]

# Back-compat alias: any downstream code still importing the legacy
# name resolves to the new conservative default.
_SCOPE_LINKEDIN = _SCOPE_LINKEDIN_DEFAULT

_FIELDS_CAMPAIGN_LINKEDIN = "id,name,test,account"
_FIELDS_STATISTIC_LINKEDIN = (
    "actionClicks,adUnitClicks,clicks,costInUsd,"
    "externalWebsiteConversions,impressions,pivotValues"
)
_URN_ORGANIZATION_LINKEDIN = "urn:li:organization:"
