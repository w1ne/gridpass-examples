# GridPass examples

Examples of grid-responsive AI data center operation. GridPass is being developed for European operators; these examples are illustrative, not a production control system.

## Facility event: sample meter data

[`examples/facility-event.csv`](examples/facility-event.csv) contains four synthetic 15-minute intervals. A grid request sets a 900 kW site cap. The rows show an illustrative baseline and site meter readings. They are invented values, not measurements or a customer result.

| Interval | Baseline | Cap | Meter |
| --- | ---: | ---: | ---: |
| 12:00–12:15 | 1,000 kW | 900 kW | 890 kW |
| 12:15–12:30 | 1,020 kW | 900 kW | 900 kW |
| 12:30–12:45 | 980 kW | 900 kW | 910 kW |
| 12:45–13:00 | 990 kW | 900 kW | 900 kW |

The third interval is 10 kW above the requested cap. A real assessment must use an agreed baseline, trustworthy time-aligned site meters, workload performance, and the relevant provider's rules. An accepted request or GPU power-limit change does not prove site-level compliance.

## Facility event: cap and energy analysis

[`examples/analyze_facility_event.py`](examples/analyze_facility_event.py) reads the sample CSV, finds intervals above the cap, and totals energy. It uses only the Python standard library and was tested with Python 3.14. It reads one local file and does nothing else.

```console
$ python3 examples/analyze_facility_event.py examples/facility-event.csv
Event: 2026-01-15 12:00Z to 13:00Z, 4 intervals, 1 h
Tolerance: 0 kW

Cap breaches: 1
  12:30-12:45  meter 910 kW > cap 900 kW  (+10 kW, +2.5 kWh)

Baseline energy:     997.5 kWh
Cap energy budget:   900.0 kWh
Metered energy:      900.0 kWh
Reduction vs base:   97.5 kWh
Energy above cap:    2.5 kWh

Synthetic, illustrative analysis; not a compliance or settlement result.
```

The exit code is `0` when no interval exceeds the cap, `1` when one or more intervals exceed it, and `2` when the input is invalid. Use `--tolerance-kw N` to ignore excess of `N` kW or less. For example, `--tolerance-kw 10` gives exit code `0` for the sample.

### How the numbers are calculated

- Each kW value is the average power over its interval. Energy (kWh) = kW × interval hours. A 15-minute interval is 0.25 h.
- A breach is an interval where `meter_kw > cap_kw + tolerance`. A meter value equal to the cap is not a breach.
- Energy above cap = sum of (`meter_kw` − `cap_kw`) × hours over the breach intervals only. Intervals below the cap do not offset a breach.
- Reduction vs base = baseline energy − metered energy.

The sample shows why a per-interval check matters. Metered energy (900.0 kWh) equals the cap energy budget (900.0 kWh), so an event-level total looks compliant. The 12:30–12:45 interval is still 10 kW above the cap; the 890 kW interval at 12:00 hides it in the total.

### Input format

The input is a UTF-8 CSV file with one header row and one row per interval.

- The header must contain exactly these five columns, each once, in any order: `start_utc`, `end_utc`, `baseline_kw`, `cap_kw`, `meter_kw`. Missing, duplicate and unknown columns are errors.
- Each row must have exactly one field per header column. Short rows and rows with extra fields are errors. Blank lines are ignored.
- `start_utc` and `end_utc` are ISO 8601 times with a UTC offset or `Z`, for example `2026-01-15T12:00:00Z`. The script converts them to UTC; a time that falls outside years 1–9999 after conversion is an error. Each `end_utc` must be after its `start_utc`.
- `baseline_kw`, `cap_kw` and `meter_kw` are finite decimal numbers in kW. `nan`, `inf` and other non-finite values are errors.
- Rows may be in any order. After sorting by start time, the intervals must be contiguous: each interval starts exactly when the previous one ends. An overlap is an error. A gap is also an error, because meter coverage in the gap is unknown.

For invalid input, the script prints `error: ...` to standard error, prints no report, and exits with code `2`. A missing or unreadable file, a non-UTF-8 file, and a non-finite or negative `--tolerance-kw` value also give exit code `2`. Error messages quote values and column names from the file with Python escapes, so control characters in the input cannot change the terminal.

The report prints times as `HH:MM` when they fall on the event start date. Times on a later date, for example in an overnight event, include the full date.

### Tests

```console
$ python3 -m unittest discover -s examples
```

The tests in [`examples/test_analyze_facility_event.py`](examples/test_analyze_facility_event.py) cover parsing and validation (column, row, number, time, gap and overlap errors), breach edge cases (equal to cap, tolerance limits), overnight report dates, energy totals for the sample file, and command-line exit codes for valid and malformed input.

## Scope and safety

The examples are offline and synthetic. They do not connect to a grid, scheduler, GPU, battery, or energy management system. Do not use them to operate equipment or claim contractual compliance. GridPass's core product code is maintained separately and is not included here.

## License

The original example code, data and documentation in this repository are available under the MIT License. See [`LICENSE`](LICENSE). No third-party code or production data is included.
