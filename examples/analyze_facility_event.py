#!/usr/bin/env python3
"""Analyze synthetic facility-event meter data for cap breaches and energy.

Educational example. Reads a local CSV only. It does not connect to any
network, meter, scheduler or equipment, and its output is not a compliance
or settlement result.

Usage:
    python3 analyze_facility_event.py facility-event.csv [--tolerance-kw 0]

Exit code: 0 if no interval exceeds cap + tolerance, 1 if one or more do,
2 if the input is invalid.

SPDX-License-Identifier: MIT
"""

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

REQUIRED_COLUMNS = ("start_utc", "end_utc", "baseline_kw", "cap_kw", "meter_kw")
POWER_COLUMNS = ("baseline_kw", "cap_kw", "meter_kw")


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime
    baseline_kw: float
    cap_kw: float
    meter_kw: float

    @property
    def hours(self):
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True)
class Breach:
    interval: Interval
    excess_kw: float

    @property
    def excess_kwh(self):
        return self.excess_kw * self.interval.hours


@dataclass(frozen=True)
class Summary:
    duration_hours: float
    baseline_kwh: float
    cap_kwh: float
    metered_kwh: float
    breach_count: int
    excess_kwh: float

    @property
    def reduction_kwh(self):
        """Baseline energy minus metered energy (positive = less consumed)."""
        return self.baseline_kwh - self.metered_kwh


def _parse_utc(text, column, line):
    try:
        if not text.isprintable():  # fromisoformat ignores a trailing NUL
            raise ValueError
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"line {line}: {column} is not an ISO 8601 time: {text!r}") from None
    if value.tzinfo is None:
        raise ValueError(f"line {line}: {column} must include a UTC offset or 'Z'")
    try:
        return value.astimezone(timezone.utc)
    except OverflowError:
        raise ValueError(f"line {line}: {column} is outside the UTC range: {text!r}") from None


def _parse_kw(text, column, line):
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError(f"line {line}: {column} is not a number: {text!r}") from None
    if not math.isfinite(value):
        raise ValueError(f"line {line}: {column} must be a finite number: {text!r}")
    return value


def _fmt_time(t, ref_date=None):
    """HH:MM if t falls on ref_date, otherwise the full date and time."""
    return f"{t:%H:%M}" if t.date() == ref_date else f"{t:%Y-%m-%d %H:%M}"


def _names(columns):
    """Quote column names with repr() so control characters print escaped."""
    return ", ".join(map(repr, columns))


def _read_header(reader):
    header = next(reader, None) or []
    duplicates = sorted({c for c in header if header.count(c) > 1})
    if duplicates:
        raise ValueError(f"duplicate column(s): {_names(duplicates)}")
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"missing column(s): {', '.join(missing)}")
    unknown = [c for c in header if c not in REQUIRED_COLUMNS]
    if unknown:
        raise ValueError(f"unknown column(s): {_names(unknown)}")
    return header


def parse_intervals(f):
    """Read intervals from a CSV file object and validate them.

    The header must name each required column exactly once, in any order, and
    every row must have one field per column. Intervals must have a positive
    duration and must be contiguous: no overlaps and no gaps, because a gap is
    time with unknown meter coverage.
    """
    reader = csv.reader(f, strict=True)
    header = _read_header(reader)

    rows = []
    for fields in reader:
        line = reader.line_num
        if not fields:
            continue  # blank line
        if len(fields) != len(header):
            raise ValueError(f"line {line}: expected {len(header)} fields, got {len(fields)}")
        record = dict(zip(header, fields))
        start = _parse_utc(record["start_utc"], "start_utc", line)
        end = _parse_utc(record["end_utc"], "end_utc", line)
        if end <= start:
            raise ValueError(f"line {line}: end_utc must be after start_utc")
        kw = {c: _parse_kw(record[c], c, line) for c in POWER_COLUMNS}
        rows.append((line, Interval(start, end, **kw)))

    if not rows:
        raise ValueError("no intervals in input")

    rows.sort(key=lambda item: item[1].start)
    for (_, prev), (line, cur) in zip(rows, rows[1:]):
        if cur.start < prev.end:
            raise ValueError(
                f"line {line}: interval overlaps the one ending {_fmt_time(prev.end)}Z"
            )
        if cur.start > prev.end:
            raise ValueError(
                f"line {line}: gap from {_fmt_time(prev.end)}Z to {_fmt_time(cur.start)}Z "
                "(meter coverage unknown)"
            )
    return [interval for _, interval in rows]


def find_cap_breaches(rows, tolerance_kw=0.0):
    """Return intervals whose average meter power exceeds cap + tolerance."""
    if not math.isfinite(tolerance_kw):
        raise ValueError("tolerance_kw must be finite")
    if tolerance_kw < 0:
        raise ValueError("tolerance_kw must not be negative")
    return [
        Breach(r, r.meter_kw - r.cap_kw)
        for r in rows
        if r.meter_kw > r.cap_kw + tolerance_kw
    ]


def summarize(rows, tolerance_kw=0.0):
    """Energy totals (kWh) over the event. Each kW value is an interval average."""
    breaches = find_cap_breaches(rows, tolerance_kw)
    return Summary(
        duration_hours=sum(r.hours for r in rows),
        baseline_kwh=sum(r.baseline_kw * r.hours for r in rows),
        cap_kwh=sum(r.cap_kw * r.hours for r in rows),
        metered_kwh=sum(r.meter_kw * r.hours for r in rows),
        breach_count=len(breaches),
        excess_kwh=sum(b.excess_kwh for b in breaches),
    )


def _fmt(x):
    return f"{x:g}"


def format_report(rows, tolerance_kw=0.0):
    breaches = find_cap_breaches(rows, tolerance_kw)
    s = summarize(rows, tolerance_kw)
    day = rows[0].start.date()
    lines = [
        f"Event: {_fmt_time(rows[0].start)}Z to {_fmt_time(rows[-1].end, day)}Z, "
        f"{len(rows)} intervals, {_fmt(s.duration_hours)} h",
        f"Tolerance: {_fmt(tolerance_kw)} kW",
        "",
        f"Cap breaches: {s.breach_count}",
    ]
    for b in breaches:
        r = b.interval
        same_day = r.start.date() == r.end.date() == day
        ref = day if same_day else None
        lines.append(
            f"  {_fmt_time(r.start, ref)}-{_fmt_time(r.end, ref)}  meter {_fmt(r.meter_kw)} kW > cap {_fmt(r.cap_kw)} kW"
            f"  (+{_fmt(b.excess_kw)} kW, +{_fmt(b.excess_kwh)} kWh)"
        )
    lines += [
        "",
        f"Baseline energy:     {s.baseline_kwh:.1f} kWh",
        f"Cap energy budget:   {s.cap_kwh:.1f} kWh",
        f"Metered energy:      {s.metered_kwh:.1f} kWh",
        f"Reduction vs base:   {s.reduction_kwh:.1f} kWh",
        f"Energy above cap:    {s.excess_kwh:.1f} kWh",
        "",
        "Synthetic, illustrative analysis; not a compliance or settlement result.",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv_path", help="CSV with start_utc,end_utc,baseline_kw,cap_kw,meter_kw")
    parser.add_argument(
        "--tolerance-kw", type=float, default=0.0,
        help="ignore excess at or below this many kW (default: 0)",
    )
    args = parser.parse_args(argv)
    try:
        with open(args.csv_path, newline="", encoding="utf-8") as f:
            rows = parse_intervals(f)
        report = format_report(rows, args.tolerance_kw)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(report)
    return 1 if find_cap_breaches(rows, args.tolerance_kw) else 0


if __name__ == "__main__":
    sys.exit(main())
