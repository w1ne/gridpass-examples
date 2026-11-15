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

## Scope and safety

The examples are offline and synthetic. They do not connect to a grid, scheduler, GPU, battery, or energy management system. Do not use them to operate equipment or claim contractual compliance. GridPass's core product code is maintained separately and is not included here.

## License

The original example data and documentation in this repository are available under the MIT License. No third-party code or production data is included.
