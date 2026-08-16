# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.addons.social_media_base.social_utils import social_url_encode

_URL_FEED_UPDATE_LINKEDIN = "https://www.linkedin.com/feed/update/"
_URL_REST_LINKEDIN = "https://api.linkedin.com/rest"
_URL_V2_LINKEDIN = "https://api.linkedin.com/v2"
_URL_AUTH_V2_LINKEDIN = "https://www.linkedin.com/oauth/v2"

_VERSION_STRING_LINKEDIN = "202607"

# Months of statistics the chart sums up as the figures of the account. The
# analytics endpoints keep about a year of history, so asking for more adds
# empty buckets and nothing else.
_CHART_HISTORY_MONTHS_LINKEDIN = 12

_HEADERS_LINKEDIN = {
    "X-Restli-Protocol-Version": "2.0.0",
    "LinkedIn-Version": _VERSION_STRING_LINKEDIN,
}

_SCOPE_LINKEDIN = [
    "profile",
    "r_organization_social",
    "rw_organization_admin",
    "w_member_social",
    "w_organization_social",
    "r_basicprofile",
    "r_organization_admin",
    "email",
    "r_1st_connections_size",
]

# The formats the media APIs of LinkedIn take. Images API: "JPG, GIF, and PNG
# formats". Videos API: "File format: MP4".
_IMAGE_MIMETYPES_LINKEDIN = ("image/jpeg", "image/png", "image/gif")
_VIDEO_MIMETYPES_LINKEDIN = ("video/mp4",)

_URN_ORGANIZATION_LINKEDIN = "urn:li:organization:"
_URN_IMAGE_LINKEDIN = "urn:li:image:"
_URN_VIDEO_LINKEDIN = "urn:li:video:"
_URN_SHARE_LINKEDIN = "urn:li:share:"
_URN_UGC_POST_LINKEDIN = "urn:li:ugcPost:"

# The criteria of the organization finder, which the endpoints answering a
# single entity by URN do not take.
_FINDER_PARAMS_LINKEDIN = ("q", "organizationalEntity")

# Days of daily buckets the check for updates watches. The window has to be
# wider than the interval of the cron so a bucket is compared against itself at
# least once before ageing out of it, and wide enough to still catch a figure
# LinkedIn revises a few days late.
_UPDATE_CHECK_DAYS_LINKEDIN = 7

# Which figures of a daily bucket are watched, by their position in the tuple
# ``_get_linkedin_chart_statistics`` builds: clicks, likes, comments, shares
# and impressions. The engagement (position 4) is left out on purpose: it is a
# ratio of the other figures over the impressions, so it cannot move without
# one of them moving, and it is the only float of the set.
_UPDATE_CHECK_FIGURES_LINKEDIN = (0, 1, 2, 3, 5)

_VIDEO_UPLOAD_PART_SIZE_LINKEDIN = 4 * 1024 * 1024

# The Posts API answers at most 100 posts per page, and it may answer fewer
# than asked while there are still posts left, so a page is only the last one
# when it comes back empty. The number of pages is capped to keep a feed that
# never ends from looping forever.
_POSTS_PAGE_SIZE_LINKEDIN = 100
_POSTS_MAX_PAGES_LINKEDIN = 50

# LinkedIn answers 414 to a query string longer than 4 KB, and the statistics
# endpoints take the URN of every post in it. Neither of them paginates, so
# the URNs are the only thing that can be split. The margin covers the rest of
# the query string and what percent-encoding adds to the URNs.
_QUERY_STRING_MAX_BYTES_LINKEDIN = 4096
_QUERY_STRING_MARGIN_BYTES_LINKEDIN = 512

# How many days before its expiry date a token is treated as expired. The
# check runs before every publication and on the schedule of the updates
# cron, and a token renewed at the last moment is one that a post planned
# for the weekend would not find.
_TOKEN_MARGIN_DAYS_LINKEDIN = 7

_VIDEO_POLL_ATTEMPTS_LINKEDIN = 30
_VIDEO_POLL_DELAY_LINKEDIN = 2

_ERROR_DETAIL_KEYS_LINKEDIN = ("error_description", "message")
_ERROR_CODE_KEYS_LINKEDIN = ("error", "serviceErrorCode")
_ERROR_INPUT_KEYS_LINKEDIN = ("inputErrors", "conditionalInputErrors")

_ERROR_CREDENTIALS_CODES_LINKEDIN = (
    "invalid_client",
    "invalid_grant",
    "invalid_request",
    "invalid_token",
    "REVOKED_ACCESS_TOKEN",
    "EXPIRED_ACCESS_TOKEN",
)


def _encoded_urns_bytes(urns, param_field):
    """Return what the URNs weigh in a query string, once encoded.

    Measured through the very function that builds the parameter, so the
    ``List(...)`` wrapper and the percent-encoding are counted as they will
    be sent.

    :param urns: the URNs of one batch.
    :param param_field: the name of the query parameter carrying them.
    :rtype: int
    """
    encoded = social_url_encode(param_field, {param_field: [",".join(urns)]}, None)
    return len(encoded.encode())


def _batch_urns_by_url_size(urns, param_field, fixed_query_bytes=0):
    """Split the URNs into batches whose query string LinkedIn accepts.

    The statistics endpoints take every URN in the query string and none of
    them paginates, so a feed of more than about a hundred posts can only be
    read in several calls. The cut is made on the encoded size rather than on
    a fixed number of URNs because their length varies and the encoding does
    not grow linearly with it.

    A URN too long to fit on its own is still given its own batch: LinkedIn
    refusing one call is better than never making it.

    :param urns: the URNs to split, in the order they should be asked for.
    :param param_field: the name of the query parameter carrying them.
    :param fixed_query_bytes: what the rest of the query string weighs.
    :return: the batches of URNs, empty when there is nothing to ask for.
    :rtype: list
    """
    budget = (
        _QUERY_STRING_MAX_BYTES_LINKEDIN
        - _QUERY_STRING_MARGIN_BYTES_LINKEDIN
        - fixed_query_bytes
    )
    batches = []
    batch = []
    for urn in urns:
        if batch and _encoded_urns_bytes(batch + [urn], param_field) > budget:
            batches.append(batch)
            batch = [urn]
        else:
            batch.append(urn)
    if batch:
        batches.append(batch)
    return batches


def _linkedin_statistics_checkpoint(statistics):
    """Return the stored form of the daily buckets of a page.

    Kept as sorted JSON so the value is stable whatever order LinkedIn
    answered the buckets in.

    :param statistics: the buckets as ``_get_linkedin_recent_statistics``
        returns them, keyed by day.
    :return: the value to store, empty when there is nothing to compare.
    :rtype: str
    """
    if not statistics:
        return ""
    return json.dumps(
        {period: list(figures) for period, figures in statistics.items()},
        sort_keys=True,
    )


def _linkedin_statistics_snapshot(checkpoint):
    """Read back a checkpoint, ignoring anything that is not one.

    The value comes from a stored column, so it is validated instead of
    trusted: a checkpoint written by an older version of this check, or edited
    by hand, must read as "no baseline yet" rather than compare wrongly.

    :param checkpoint: the stored value.
    :return: the buckets by day, empty when there is nothing usable.
    :rtype: dict
    """
    if not checkpoint:
        return {}
    try:
        snapshot = json.loads(checkpoint)
    except ValueError:
        return {}
    if not isinstance(snapshot, dict):
        return {}
    return {
        period: figures
        for period, figures in snapshot.items()
        if isinstance(figures, list)
        and all(isinstance(figure, int | float) for figure in figures)
    }


def _linkedin_statistics_moved(previous, current):
    """Tell whether the daily buckets carry activity the last import missed.

    Buckets are compared day by day and never as a whole: the window slides,
    so the oldest day of the previous reading is gone from this one, and
    comparing the two sets would report a change every single day.

    A day missing from the previous reading only counts when it carries
    activity. LinkedIn answers a bucket of zeros for a day with nothing on it,
    and the day in progress starts as one of those: announcing it would mean
    announcing updates every midnight.

    A day gone from this reading is ignored: it aged out of the window, which
    is not activity.

    :param previous: the buckets of the last import.
    :param current: the buckets read now.
    :return: whether anything moved.
    :rtype: bool
    """
    if not previous:
        return False
    for period, figures in current.items():
        stored = previous.get(period)
        if stored is None:
            if any(figures):
                return True
        elif list(stored) != list(figures):
            return True
    return False


def _linkedin_error_inputs(payload):
    """Return the per-field explanations of a LinkedIn validation error.

    :param payload: the parsed answer of LinkedIn.
    :return: one description per rejected field, in the order LinkedIn
        reported them.
    :rtype: list
    """
    details = payload.get("errorDetails")
    if not isinstance(details, dict):
        return []
    descriptions = []
    for key in _ERROR_INPUT_KEYS_LINKEDIN:
        for input_error in details.get(key) or []:
            description = isinstance(input_error, dict) and input_error.get(
                "description"
            )
            if description:
                descriptions.append(str(description))
    return descriptions


def _linkedin_error_payload(error):
    """Return the answer of LinkedIn as a dict, when it is one.

    :param error: a ``requests.Response``, a parsed body, or anything that
        was raised while talking to LinkedIn.
    :return: the parsed body, or an empty dict when it is not JSON.
    :rtype: dict
    """
    if isinstance(error, dict):
        return error
    body = getattr(error, "text", None)
    if body is None:
        body = str(error)
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _linkedin_error_detail(error):
    """Return what LinkedIn answered, in a readable form.

    A validation error is reported field by field, since its ``message``
    only says that something failed. The answer of LinkedIn is never
    dropped: when it carries no known key, or when it is not JSON at all,
    its body is returned as it is.

    :rtype: str
    """
    payload = _linkedin_error_payload(error)
    inputs = _linkedin_error_inputs(payload)
    if inputs:
        return "\n".join(inputs)
    for key in _ERROR_DETAIL_KEYS_LINKEDIN:
        detail = payload.get(key)
        if detail:
            return str(detail)
    body = getattr(error, "text", None)
    if body is None:
        body = str(error)
    return str(body).strip()


def _linkedin_error_code(error):
    """Return the code that names an error of LinkedIn, if it has one.

    :rtype: str
    """
    payload = _linkedin_error_payload(error)
    for key in _ERROR_CODE_KEYS_LINKEDIN:
        code = payload.get(key)
        if code:
            return str(code)
    return ""


def _linkedin_is_credentials_error(error):
    """Return whether LinkedIn refused the authorization of the account.

    Those are the only errors worth retrying after renewing the token, so
    they are told apart from everything else LinkedIn may refuse. The HTTP
    status is checked too: an expired token is answered with a 401 that does
    not always carry one of the known codes.

    :param error: a ``requests.Response`` or the parsed answer of LinkedIn.
    :rtype: bool
    """
    if getattr(error, "status_code", None) == 401:
        return True
    return _linkedin_error_code(error) in _ERROR_CREDENTIALS_CODES_LINKEDIN
