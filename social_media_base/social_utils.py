# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlencode

import pytz

from odoo import _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT


def convert_to_days(seconds=None, milliseconds=None):
    """
    Converts the given duration in seconds or milliseconds into days.

    :param int seconds: duration in seconds
    :param int milliseconds: duration in milliseconds
    :return: duration in days
    :rtype: int
    """
    if seconds:
        return seconds / 60 / 60 / 24
    elif milliseconds:
        return milliseconds / 1000 / 60 / 60 / 24
    return 0


def convert_to_date(
    date_add=None,
    seconds=None,
    milliseconds=None,
    expire_date=True,
    time_zone=None,
    format_date=None,
):
    if time_zone and isinstance(time_zone, str):
        time_zone = pytz.timezone(time_zone)
    if expire_date:
        if not date_add:
            date_add = date.today()
        return_date = date_add + timedelta(days=convert_to_days(seconds, milliseconds))
    else:
        return_date = datetime.fromtimestamp(milliseconds / 1000, tz=time_zone)
    if format_date:
        return_date = return_date.strftime(format_date)
    return return_date


def convert_date_in_time(milliseconds, timezone=None):
    timezone = timezone if timezone else pytz.utc
    if isinstance(timezone, str):
        timezone = pytz.timezone(timezone)
    val_date = convert_to_date(
        milliseconds=milliseconds, expire_date=False, time_zone=timezone
    )
    current_date = datetime.now(timezone)
    diff_date = current_date - val_date
    seconds = diff_date.total_seconds()
    minutes = seconds / 60
    hours = minutes / 60
    days = hours / 24
    months = days / 30
    years = months / 12

    if seconds < 60:
        date_in_time = _("%(count)s seconds", count=int(seconds))
    elif minutes < 60:
        date_in_time = _("%(count)s minutes", count=int(minutes))
    elif hours < 24:
        date_in_time = _("%(count)s hours", count=int(hours))
    elif days < 30:
        date_in_time = _("%(count)s days", count=int(days))
    elif months < 12:
        date_in_time = _("%(count)s months", count=int(months))
    else:
        date_in_time = _(
            "%(years)s years and %(months)s months",
            years=int(years),
            months=int(months % 12),
        )
    return date_in_time


def replace_repetitions(text, character_replace, character_new, repetitions):
    """Replace only the requested occurrences of a substring.

    Unlike ``str.replace``, which replaces every occurrence or the first
    ``n`` ones, this picks the occurrences by their position: ``["1", "3"]``
    replaces the first and the third and leaves the second alone.

    :param str text: the text to rewrite.
    :param str character_replace: the substring being replaced.
    :param str character_new: what to put in its place.
    :param repetitions: the 1-based positions to replace, as strings.
    :rtype: str
    """
    positions = [m.start() for m in re.finditer(re.escape(character_replace), text)]
    text_result = list(text)
    count = 0
    for repetition in repetitions:
        if int(repetition) - 1 < len(positions):
            if count == 0:
                start = positions[int(repetition) - 1]
                count += 1
            else:
                start = positions[int(repetition) - 1] - (
                    (len(character_replace) - 1) * count
                )
                count += 1
            fin = start + len(character_replace)
            text_result[start:fin] = character_new
    return "".join(text_result)


def social_url_encode(
    param_field, params_values, params_values_char_ignore, format_quote=False
):
    """Encode one query parameter the way the social media APIs expect it.

    ``urlencode`` is not enough because those APIs read a list as
    ``List(a,b,c)`` and refuse the percent-encoded parentheses and commas,
    and because each of them tolerates a different subset of characters
    unencoded.

    :param str param_field: the key of ``params_values`` being encoded.
    :param dict params_values: the whole set of parameter values.
    :param dict params_values_char_ignore: per parameter, the characters to
        leave unencoded. Each entry maps a selector to a character: ``all``
        restores every occurrence, and ``"1,3"`` restores only the first and
        the third one, which is what an API needs when the same character
        separates values at one level and delimits them at another.
    :param bool format_quote: quote the value even when it is not a list.
    :rtype: str
    """
    values = {param_field: params_values[param_field]}
    if isinstance(params_values[param_field], list):
        values = (
            "List("
            + ",".join(
                quote(str(param_value), safe=",")
                for param_value in params_values[param_field]
            )
            + ")"
        )
        # quote() encodes a space as '+' inside the list, and the APIs read
        # that '+' as a literal character instead of a separator, so it is
        # dropped rather than restored.
        url_format = f"{param_field}={quote(values, safe='()%,')}".replace("+", "")
    elif format_quote:
        url_format = (
            f"{param_field}={quote(str(params_values[param_field]), safe='()%,')}"
        )
    else:
        url_format = urlencode(values)
    if params_values_char_ignore and params_values_char_ignore.get(param_field, False):
        for params_values_char in params_values_char_ignore[param_field]:
            for key, character in params_values_char.items():
                if quote(character) in url_format and key == "all":
                    url_format = url_format.replace(quote(character), character)
                else:
                    url_format = replace_repetitions(
                        url_format, quote(character), character, key.split(",")
                    )
    return url_format


def generate_timestamps(date_start=None, date_end=None):
    """Return a ``(start, end)`` range as milliseconds since the epoch.

    Defaults to a window starting now and lasting thirty days, which is what
    the social media APIs expect when no explicit range is given.

    :rtype: tuple
    """
    if isinstance(date_start, str):
        date_start = datetime.strptime(date_start, DEFAULT_SERVER_DATE_FORMAT)
    if isinstance(date_end, str):
        date_end = datetime.strptime(date_end, DEFAULT_SERVER_DATE_FORMAT)

    if date_start:
        date_start_time = date_start.timestamp() * 1000
    else:
        date_start_time = datetime.now().timestamp() * 1000

    if date_end:
        date_end_time = date_end.timestamp() * 1000
    else:
        date_end_time = date_start_time + (30 * 86400000)
    return int(date_start_time), int(date_end_time)


def get_chart_periods(start_date, end_date, freq="W-MON"):
    """Return the periods of a chart range, as ``(key, label)`` pairs.

    The key is what the statistics of a social media are aligned on, so it
    has to be derivable from a date alone; the label is what the chart
    prints on its axis.

    :param freq: ``D`` for days, ``ME`` for months, ``W-MON`` for weeks
                 starting on monday.
    :raises UserError: when the frequency is not one of those three.
    :rtype: list
    """
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date)

    result = []

    if freq == "D":
        current = start_date
        while current <= end_date:
            result.append((current.strftime("%Y-%m-%d"), current.strftime("%d/%m/%Y")))
            current += timedelta(days=1)

    elif freq == "ME":
        current = start_date.replace(day=1)
        while current <= end_date:
            next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
            last_day = next_month - timedelta(days=1)
            if last_day <= end_date:
                result.append((last_day.strftime("%Y-%m"), last_day.strftime("%m/%Y")))
            current = next_month

    elif freq == "W-MON":
        days_ahead = (0 - start_date.weekday()) % 7
        current = start_date + timedelta(days=days_ahead)
        while current <= end_date:
            result.append((current.strftime("%Y-W%W"), current.strftime("%W/%Y")))
            current += timedelta(weeks=1)

    else:
        raise UserError(_("Unsupported frequency: %(freq)s", freq=freq))

    return result


def get_chart_period_key(date_value, freq="W-MON"):
    """Return the key of ``get_chart_periods`` a date belongs to.

    Connectors call it to align the statistics of one bucket of their API
    with the periods of the chart.

    :param date_value: a ``datetime`` or an ISO string.
    :rtype: str
    """
    if isinstance(date_value, str):
        date_value = datetime.fromisoformat(date_value)
    if freq == "D":
        return date_value.strftime("%Y-%m-%d")
    if freq == "ME":
        return date_value.strftime("%Y-%m")
    if freq == "W-MON":
        # The week a date belongs to is the one of the monday before it, the
        # same day get_chart_periods walks on.
        monday = date_value - timedelta(days=date_value.weekday())
        return monday.strftime("%Y-W%W")
    raise UserError(_("Unsupported frequency: %(freq)s", freq=freq))
