EDA scripts (run against the NDA'd BMW data, expected at /home/ubuntu/bmw/data and /home/ubuntu/bmw/full):
- eda.py      – first schema/range + per-rider pass on exampleUserA
- fun.py      – revealed-preference signals (re-rides, lean hotspots, mid-ride stops, ride types, twistiness, GPX names)
- insight.py  – within-ride drift, around-stops, lean vs speed, bikes, gears/rpm, temperature, repeated pairs
- crowd.py    – parallel per-trip + per-1km-cell feature extraction: `python3 crowd.py <subdir> <prefix> <limit>` → derived/<prefix>_{trips,cells}.parquet
