# Copyright 2025 Binhex <https://www.binhex.cloud>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import datetime, timedelta
from unittest.mock import patch

import pytz
from dateutil.relativedelta import relativedelta

from odoo.exceptions import UserError

from odoo.addons.social_media_base.social_utils import (
    convert_date_in_time,
    convert_to_date,
    convert_to_days,
    generate_timestamps,
    get_chart_period_key,
    get_chart_periods,
    replace_repetitions,
    social_url_encode,
)
from odoo.addons.social_media_base.tests.test_social_common import (
    TestSocialMediaBaseCommon,
)

from .test_social_common import PATCH_SOCIAL_BASE_UTILS


class TestUtilsBase(TestSocialMediaBaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixed_now = datetime(2025, 5, 30, 12, 0, 0, tzinfo=pytz.UTC)
        cls.date_start = "2025-01-01"
        cls.date_end = "2025-02-01"

    def test_convert_to_days(self):
        result = convert_to_days(seconds=50)
        self.assertEqual(result, 50 / 60 / 60 / 24)

        result = convert_to_days(milliseconds=10000)
        self.assertEqual(result, 10000 / 1000 / 60 / 60 / 24)

    def test_convert_to_date(self):
        result = convert_to_date(milliseconds=10000)
        self.assertEqual(result, datetime.now().date())

        result = convert_to_date(milliseconds=10000, time_zone="UTC")
        self.assertEqual(result, datetime.now().date())

        result = convert_to_date(
            milliseconds=10000, time_zone="UTC", date_add=datetime.now()
        )
        self.assertEqual(result.date(), datetime.now().date())

    @patch(PATCH_SOCIAL_BASE_UTILS.format("convert_to_date"))
    @patch(PATCH_SOCIAL_BASE_UTILS.format("datetime"))
    def test_convert_date_in_time(self, mock_datetime, mock_convert_to_date):
        seconds = timedelta(seconds=45)
        val_date = self.fixed_now - seconds
        mock_convert_to_date.return_value = val_date
        mock_datetime.now.return_value = self.fixed_now
        result = convert_date_in_time(milliseconds=50, timezone="UTC")
        self.assertEqual(result, "45 seconds")

        minutes = timedelta(minutes=45)
        val_date = self.fixed_now - minutes
        mock_convert_to_date.return_value = val_date
        mock_datetime.now.return_value = self.fixed_now
        result = convert_date_in_time(milliseconds=50, timezone="UTC")
        self.assertEqual(result, "45 minutes")

        hours = timedelta(hours=2)
        val_date = self.fixed_now - hours
        mock_convert_to_date.return_value = val_date
        mock_datetime.now.return_value = self.fixed_now
        result = convert_date_in_time(milliseconds=50, timezone="UTC")
        self.assertEqual(result, "2 hours")

        days = timedelta(days=2)
        val_date = self.fixed_now - days
        mock_convert_to_date.return_value = val_date
        mock_datetime.now.return_value = self.fixed_now
        result = convert_date_in_time(milliseconds=50, timezone="UTC")
        self.assertEqual(result, "2 days")

        months = relativedelta(months=2)
        val_date = self.fixed_now - months
        mock_convert_to_date.return_value = val_date
        mock_datetime.now.return_value = self.fixed_now
        result = convert_date_in_time(milliseconds=50, timezone="UTC")
        self.assertEqual(result, "2 months")

    @patch(PATCH_SOCIAL_BASE_UTILS.format("convert_to_date"))
    @patch(PATCH_SOCIAL_BASE_UTILS.format("datetime"))
    def test_convert_date_in_time_years(self, mock_datetime, mock_convert_to_date):
        """Beyond a year the two units are given, in English only."""
        mock_convert_to_date.return_value = self.fixed_now - relativedelta(
            years=2, months=3
        )
        mock_datetime.now.return_value = self.fixed_now
        result = convert_date_in_time(milliseconds=50, timezone="UTC")
        self.assertEqual(result, "2 years and 3 months")

    def test_social_url_encode(self):
        params_values = {
            "q": "authors",
            "authors": ["urn:li:organization:123456789"],
        }
        result = social_url_encode("authors", params_values, {})
        self.assertEqual(result, "authors=List(urn%3Ali%3Aorganization%3A123456789)")

        params_values = {"author": "urn:li:organization:123456789"}
        result = social_url_encode("author", params_values, {})
        self.assertEqual(result, "author=urn%3Ali%3Aorganization%3A123456789")

        params_values = {"author": "urn:li:organization:123456789"}
        result = social_url_encode("author", params_values, {"author": [{"all": ":"}]})
        self.assertEqual(result, "author=urn:li:organization:123456789")

    def test_social_url_encode_not_string_value(self):
        """Values that are not strings, such as a page size, must be encoded."""
        result = social_url_encode("count", {"count": 100}, {}, format_quote=True)
        self.assertEqual(result, "count=100")

        result = social_url_encode("ids", {"ids": [1, 2]}, {})
        self.assertEqual(result, "ids=List(1,2)")

    def test_generate_timestamps(self):
        result = generate_timestamps(date_start=self.date_start, date_end=self.date_end)
        self.assertEqual(result[0], 1735689600000)
        self.assertEqual(result[1], 1738368000000)

    def test_generate_timestamps_without_end_date(self):
        result = generate_timestamps(date_start=self.date_start)
        self.assertEqual(result[0], 1735689600000)
        self.assertEqual(result[1], result[0] + (30 * 86400000))

    def test_get_chart_periods(self):
        with self.assertRaises(UserError):
            get_chart_periods(
                start_date=self.date_start, end_date=self.date_end, freq="W-MONN"
            )

        result = get_chart_periods(
            start_date=self.date_start, end_date=self.date_end, freq="D"
        )
        self.assertEqual(len(result), 32)
        self.assertEqual(result[0], ("2025-01-01", "01/01/2025"))

        result = get_chart_periods(start_date=self.date_start, end_date=self.date_end)
        self.assertEqual(len(result), 4)

        result = get_chart_periods(
            start_date=self.date_start, end_date=self.date_end, freq="ME"
        )
        self.assertEqual(result, [("2025-01", "01/2025")])

    def test_get_chart_period_key(self):
        """A date lands on the period get_chart_periods walks on."""
        with self.assertRaises(UserError):
            get_chart_period_key(self.date_start, freq="W-MONN")

        self.assertEqual(get_chart_period_key(self.date_start, freq="D"), "2025-01-01")
        self.assertEqual(get_chart_period_key(self.date_start, freq="ME"), "2025-01")

        periods = dict(
            get_chart_periods(start_date=self.date_start, end_date=self.date_end)
        )
        self.assertIn(
            get_chart_period_key("2025-01-09", freq="W-MON"),
            periods,
            msg="A thursday belongs to the week of the monday before it.",
        )

    def test_replace_repetitions(self):
        text_test = "rep-la-ce-all"
        result = replace_repetitions(text_test, "-", "X", [3, 5, 7])
        self.assertEqual(result, "rep-la-ceXall")

    def test_replace_repetitions_multiple(self):
        """Replacing several occurrences shifts the following positions."""
        result = replace_repetitions("a-b-c-d", "-", "X", [1, 2])
        self.assertEqual(result, "aXbXc-d")

    def test_social_url_encode_positional_char_ignore(self):
        """Only the listed occurrences of the character are restored."""
        params_values = {"author": "urn:li:organization:1"}
        result = social_url_encode("author", params_values, {"author": [{"1,2": ":"}]})
        self.assertEqual(result, "author=urn:li:organization%3A1")
