"""Unit tests for analyze_facility_event.py (stdlib unittest, offline)."""

import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import analyze_facility_event as afe

SAMPLE_CSV = pathlib.Path(__file__).with_name("facility-event.csv")

HEADER = "start_utc,end_utc,baseline_kw,cap_kw,meter_kw\n"


def rows_from(text):
    return afe.parse_intervals(io.StringIO(HEADER + text))


class ParseIntervalsTest(unittest.TestCase):
    def test_parses_timestamps_and_duration(self):
        (row,) = rows_from("2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,890\n")
        self.assertEqual(row.start.isoformat(), "2026-01-15T12:00:00+00:00")
        self.assertEqual(row.hours, 0.25)
        self.assertEqual((row.baseline_kw, row.cap_kw, row.meter_kw), (1000, 900, 890))

    def test_rejects_missing_column(self):
        with self.assertRaisesRegex(ValueError, "missing column.*meter_kw"):
            afe.parse_intervals(io.StringIO("start_utc,end_utc,baseline_kw,cap_kw\n"))

    def test_rejects_non_positive_duration(self):
        with self.assertRaisesRegex(ValueError, "line 2.*end_utc must be after start_utc"):
            rows_from("2026-01-15T12:15:00Z,2026-01-15T12:15:00Z,1000,900,890\n")

    def test_rejects_non_numeric_power(self):
        with self.assertRaisesRegex(ValueError, "line 2.*meter_kw"):
            rows_from("2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,n/a\n")

    def test_rejects_overlapping_intervals(self):
        with self.assertRaisesRegex(ValueError, "line 3.*overlaps"):
            rows_from(
                "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,890\n"
                "2026-01-15T12:10:00Z,2026-01-15T12:25:00Z,1000,900,890\n"
            )

    def test_rejects_empty_file(self):
        with self.assertRaisesRegex(ValueError, "no intervals"):
            rows_from("")

    def test_rejects_nonfinite_power(self):
        for value in ("nan", "NaN", "inf", "-inf", "Infinity"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "line 2.*cap_kw.*finite"):
                    rows_from(f"2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,{value},890\n")

    def test_rejects_gap_between_intervals(self):
        with self.assertRaisesRegex(ValueError, "line 3.*gap"):
            rows_from(
                "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,890\n"
                "2026-01-15T12:30:00Z,2026-01-15T12:45:00Z,1000,900,890\n"
            )

    def test_rejects_short_row(self):
        with self.assertRaisesRegex(ValueError, "line 2.*expected 5 fields, got 4"):
            rows_from("2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900\n")

    def test_rejects_extra_field_in_row(self):
        with self.assertRaisesRegex(ValueError, "line 2.*expected 5 fields, got 6"):
            rows_from("2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,890,1\n")

    def test_rejects_duplicate_column(self):
        with self.assertRaisesRegex(ValueError, "duplicate column.*meter_kw"):
            afe.parse_intervals(io.StringIO(
                "start_utc,end_utc,baseline_kw,cap_kw,meter_kw,meter_kw\n"
                "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,890,950\n"
            ))

    def test_rejects_unknown_column(self):
        with self.assertRaisesRegex(ValueError, "unknown column.*site"):
            afe.parse_intervals(io.StringIO(
                "start_utc,end_utc,baseline_kw,cap_kw,meter_kw,site\n"
                "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,890,A\n"
            ))

    def test_rejects_time_outside_utc_range(self):
        for text in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "line 2.*start_utc.*outside the UTC range"):
                    rows_from(f"{text},2026-01-15T12:15:00Z,1000,900,890\n")

    def test_column_names_in_errors_are_escaped(self):
        cases = {
            "duplicate": HEADER.rstrip("\n") + ",\x1b[2J,\x1b[2J\n",
            "unknown": HEADER.rstrip("\n") + ",\x1b]0;x\x07\x9b‮\n",
        }
        for name, header in cases.items():
            with self.subTest(name):
                with self.assertRaises(ValueError) as ctx:
                    afe.parse_intervals(io.StringIO(header))
                message = str(ctx.exception)
                self.assertTrue(message.isprintable(), repr(message))
                self.assertIn(f"{name} column", message)

    def test_accepts_columns_in_any_order(self):
        (row,) = afe.parse_intervals(io.StringIO(
            "meter_kw,cap_kw,baseline_kw,end_utc,start_utc\n"
            "890,900,1000,2026-01-15T12:15:00Z,2026-01-15T12:00:00Z\n"
        ))
        self.assertEqual((row.baseline_kw, row.cap_kw, row.meter_kw), (1000, 900, 890))


class CapBreachTest(unittest.TestCase):
    def test_meter_equal_to_cap_is_not_a_breach(self):
        rows = rows_from("2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,900\n")
        self.assertEqual(afe.find_cap_breaches(rows), [])

    def test_reports_excess_power_and_energy(self):
        rows = rows_from("2026-01-15T12:00:00Z,2026-01-15T12:30:00Z,1000,900,940\n")
        (breach,) = afe.find_cap_breaches(rows)
        self.assertEqual(breach.excess_kw, 40)
        self.assertEqual(breach.excess_kwh, 20)  # 40 kW for 0.5 h

    def test_tolerance_suppresses_small_excess(self):
        rows = rows_from("2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,905\n")
        self.assertEqual(afe.find_cap_breaches(rows, tolerance_kw=5), [])
        self.assertEqual(len(afe.find_cap_breaches(rows, tolerance_kw=4.9)), 1)

    def test_negative_tolerance_is_rejected(self):
        with self.assertRaises(ValueError):
            afe.find_cap_breaches([], tolerance_kw=-1)

    def test_nonfinite_tolerance_is_rejected(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "tolerance_kw must be finite"):
                    afe.find_cap_breaches([], tolerance_kw=value)


class OvernightReportTest(unittest.TestCase):
    def test_report_prints_full_dates_across_midnight(self):
        rows = rows_from(
            "2026-01-15T23:45:00Z,2026-01-16T00:00:00Z,1000,900,890\n"
            "2026-01-16T00:00:00Z,2026-01-16T00:15:00Z,1000,900,950\n"
        )
        text = afe.format_report(rows)
        self.assertIn("Event: 2026-01-15 23:45Z to 2026-01-16 00:15Z,", text)
        self.assertIn("  2026-01-16 00:00-2026-01-16 00:15  meter 950 kW", text)

    def test_breach_ending_at_midnight_prints_full_dates(self):
        rows = rows_from("2026-01-15T23:45:00Z,2026-01-16T00:00:00Z,1000,900,950\n")
        text = afe.format_report(rows)
        self.assertIn("Event: 2026-01-15 23:45Z to 2026-01-16 00:00Z,", text)
        self.assertIn("  2026-01-15 23:45-2026-01-16 00:00  meter 950 kW", text)

    def test_overlap_message_prints_full_date(self):
        with self.assertRaisesRegex(ValueError, "overlaps the one ending 2026-01-16 00:15Z"):
            rows_from(
                "2026-01-15T23:45:00Z,2026-01-16T00:15:00Z,1000,900,890\n"
                "2026-01-16T00:00:00Z,2026-01-16T00:30:00Z,1000,900,890\n"
            )


class SampleFileTest(unittest.TestCase):
    """Behavior on the synthetic sample shipped in this directory."""

    def setUp(self):
        with SAMPLE_CSV.open(newline="") as f:
            self.rows = afe.parse_intervals(f)

    def test_only_third_interval_breaches_cap(self):
        breaches = afe.find_cap_breaches(self.rows)
        self.assertEqual([b.interval.start.strftime("%H:%M") for b in breaches], ["12:30"])
        self.assertEqual(breaches[0].excess_kw, 10)
        self.assertEqual(breaches[0].excess_kwh, 2.5)

    def test_energy_summary(self):
        s = afe.summarize(self.rows)
        self.assertEqual(s.duration_hours, 1.0)
        self.assertEqual(s.baseline_kwh, 997.5)
        self.assertEqual(s.cap_kwh, 900.0)
        self.assertEqual(s.metered_kwh, 900.0)
        self.assertEqual(s.reduction_kwh, 97.5)
        self.assertEqual(s.breach_count, 1)
        self.assertEqual(s.excess_kwh, 2.5)

    def test_cli_prints_report_and_exits_nonzero_on_breach(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = afe.main([str(SAMPLE_CSV)])
        text = out.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("12:30-12:45  meter 910 kW > cap 900 kW  (+10 kW, +2.5 kWh)", text)
        self.assertIn("Metered energy:      900.0 kWh", text)
        self.assertIn("not a compliance", text)

    def test_cli_exits_zero_when_tolerance_covers_breach(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(afe.main([str(SAMPLE_CSV), "--tolerance-kw", "10"]), 0)


class CliInvalidInputTest(unittest.TestCase):
    """Every kind of malformed input gives exit code 2 and no report."""

    VALID_ROW = "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,890\n"

    def run_cli(self, content, *extra_args):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp, "input.csv")
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = afe.main([str(path), *extra_args])
        return code, out.getvalue(), err.getvalue()

    def assert_invalid(self, content, *extra_args):
        code, out, err = self.run_cli(content, *extra_args)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error: "), err)
        self.assertTrue(err.rstrip("\n").isprintable(), repr(err))

    def test_malformed_inputs_exit_2(self):
        VALID_ROW = self.VALID_ROW
        cases = {
            "empty file": "",
            "header only": HEADER,
            "missing column": "start_utc,end_utc,baseline_kw,cap_kw\n",
            "duplicate column": HEADER.rstrip("\n") + ",cap_kw\n",
            "short row": HEADER + "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900\n",
            "extra field": HEADER + VALID_ROW.rstrip("\n") + ",1\n",
            "nan power": HEADER + "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,nan,900,890\n",
            "inf power": HEADER + "2026-01-15T12:00:00Z,2026-01-15T12:15:00Z,1000,900,inf\n",
            "naive time": HEADER + "2026-01-15T12:00:00,2026-01-15T12:15:00Z,1000,900,890\n",
            "gap": HEADER + VALID_ROW + "2026-01-15T12:30:00Z,2026-01-15T12:45:00Z,1000,900,890\n",
            "NUL byte": HEADER + "2026-01-15T12:00:00Z\0,2026-01-15T12:15:00Z,1000,900,890\n",
            "time below UTC range": HEADER + "0001-01-01T00:00:00+01:00,2026-01-15T12:15:00Z,1000,900,890\n",
            "time above UTC range": HEADER + "2026-01-15T12:00:00Z,9999-12-31T23:59:59-01:00,1000,900,890\n",
            "escape in column name": HEADER.rstrip("\n") + ",\x1b[2J\n" + VALID_ROW.rstrip("\n") + ",1\n",
        }
        for name, content in cases.items():
            with self.subTest(name):
                self.assert_invalid(content)

    def test_invalid_utf8_exits_2(self):
        self.assert_invalid(HEADER.encode() + b"\xff\xfe\n")

    def test_invalid_tolerance_exits_2(self):
        for value in ("nan", "inf", "-1"):
            with self.subTest(value=value):
                self.assert_invalid(HEADER + self.VALID_ROW, "--tolerance-kw", value)

    def test_missing_file_exits_2(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(afe.main(["/nonexistent/facility-event.csv"]), 2)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
