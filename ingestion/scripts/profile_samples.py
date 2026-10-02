"""Profile sample files under data/samples/ before designing the ingestion.

Usage:
    python ingestion/scripts/profile_samples.py [samples_dir]
"""

import io
import json
import sys
from pathlib import Path

import pandas as pd

ENCODING = "cp932"


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding=ENCODING).splitlines()


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def describe_values(s: pd.Series, name: str) -> None:
    print(
        f"  {name}: count={s.count()} null={s.isna().sum()} "
        f"min={s.min()} max={s.max()} mean={s.mean():.1f}"
    )


def check_hourly_continuity(ts: pd.Series, label: str) -> None:
    expected = pd.date_range(ts.min(), ts.max(), freq="h")
    missing = expected.difference(ts)
    dup = ts[ts.duplicated()]
    print(f"  {label}: period={ts.min()} - {ts.max()}")
    print(f"  expected hours={len(expected)} actual rows={len(ts)}")
    print(f"  missing hours={len(missing)} {list(missing[:5])}")
    print(f"  duplicated timestamps={len(dup)} {list(dup[:5])}")


def profile_yearly(path: Path) -> None:
    section(f"[power / yearly] {path.name}")
    lines = read_lines(path)
    print("  first 4 lines:")
    for line in lines[:4]:
        print(f"    {line!r}")

    header_idx = next(i for i, line in enumerate(lines) if line.startswith("DATE,TIME"))
    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    print(f"  header line index={header_idx} columns={list(df.columns)}")

    times = sorted(df["TIME"].unique(), key=lambda t: int(t.split(":")[0]))
    print(f"  TIME values: {times[0]} ... {times[-1]} ({len(times)} kinds)")

    ts = pd.to_datetime(df["DATE"] + " " + df["TIME"], format="%Y/%m/%d %H:%M")
    check_hourly_continuity(ts, "timestamp")
    describe_values(df.iloc[:, 2], df.columns[2])

    daily_rows = df.groupby("DATE").size()
    print(f"  days with != 24 rows: {(daily_rows != 24).sum()}")


def split_sections(lines: list[str]) -> list[list[str]]:
    sections, current = [], []
    for line in lines[1:]:
        if line.strip():
            current.append(line)
        elif current:
            sections.append(current)
            current = []
    if current:
        sections.append(current)
    return sections


def profile_daily(dir_path: Path) -> pd.DataFrame:
    files = sorted(dir_path.glob("*_power_usage.csv"))
    section(f"[power / daily] {dir_path.name} ({len(files)} files)")

    first = read_lines(files[0])
    print(f"  first line: {first[0]!r}")
    print("  sections (header line / data rows):")
    for sec in split_sections(first):
        print(f"    rows={len(sec) - 1:>3}  {sec[0]}")

    hourly_frames, five_min_frames, structures = [], [], set()
    for f in files:
        secs = split_sections(read_lines(f))
        structures.add(tuple(s[0] for s in secs))
        for sec in secs:
            if not sec[0].startswith("DATE,TIME"):
                continue
            df = pd.read_csv(io.StringIO("\n".join(sec)))
            target = five_min_frames if "５分間隔値" in sec[0] else hourly_frames
            target.append(df)
    print(f"  distinct section structures across files: {len(structures)}")

    hourly = pd.concat(hourly_frames, ignore_index=True)
    hourly["ts"] = pd.to_datetime(hourly["DATE"] + " " + hourly["TIME"], format="%Y/%m/%d %H:%M")
    five = pd.concat(five_min_frames, ignore_index=True)
    five["ts"] = pd.to_datetime(five["DATE"] + " " + five["TIME"], format="%Y/%m/%d %H:%M")

    print("\n  hourly section:")
    check_hourly_continuity(hourly["ts"], "timestamp")
    for col in hourly.columns[2:6]:
        describe_values(hourly[col], col)

    print("\n  5-minute section:")
    print(f"  rows={len(five)} (expected {len(files) * 288})")
    for col in five.columns[2:5]:
        describe_values(five[col], col)

    # Which hour does the hourly value "H:00" represent?
    # Compare it with the mean of 5-minute values in [H, H+1) and [H-1, H).
    actual_col = hourly.columns[2]
    five_col = five.columns[2]
    fwd = five.set_index("ts")[five_col].resample("h", label="left", closed="left").mean()
    bwd = five.set_index("ts")[five_col].resample("h", label="right", closed="left").mean()
    cmp = (
        hourly.set_index("ts")[[actual_col]]
        .join(fwd.rename("mean_H_to_H+1"))
        .join(bwd.rename("mean_H-1_to_H"))
        .dropna()
    )
    for col in ["mean_H_to_H+1", "mean_H-1_to_H"]:
        diff = (cmp[actual_col] - cmp[col]).abs()
        print(f"  |hourly - {col}|: mean={diff.mean():.1f} max={diff.max():.1f}")

    return hourly[["ts", actual_col]].rename(columns={actual_col: "demand_10mw"})


def profile_weather(path: Path) -> pd.DataFrame:
    section(f"[weather] {path.name}")
    data = json.loads(path.read_text(encoding="utf-8"))
    meta = {k: v for k, v in data.items() if not isinstance(v, dict)}
    print(f"  metadata: {meta}")
    print(f"  units: {data['hourly_units']}")

    df = pd.DataFrame(data["hourly"])
    print(f"  time format sample: {df['time'].iloc[:2].tolist()}")
    df["ts"] = pd.to_datetime(df["time"])
    check_hourly_continuity(df["ts"], "time")
    for col in df.columns.drop(["time", "ts"]):
        describe_values(df[col], col)
    return df.drop(columns="time")


def profile_join(demand: pd.DataFrame, weather: pd.DataFrame) -> None:
    section("[join] daily power x weather")
    merged = demand.merge(weather, on="ts", how="inner")
    print(f"  demand rows={len(demand)} weather rows={len(weather)} joined={len(merged)}")
    if merged.empty:
        print("  no overlapping period")
        return
    hourly_corr = merged["demand_10mw"].corr(merged["temperature_2m"])
    print(f"  corr(demand, temperature_2m) = {hourly_corr:.3f}")

    daily = (
        merged.set_index("ts").resample("D").agg({"demand_10mw": "max", "temperature_2m": "max"})
    )
    print(
        f"  corr(daily max demand, daily max temp) = "
        f"{daily['demand_10mw'].corr(daily['temperature_2m']):.3f}"
    )


def main() -> None:
    samples = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/samples")

    for path in sorted(samples.glob("juyo-*.csv")):
        profile_yearly(path)

    demand = None
    for dir_path in sorted(p for p in samples.iterdir() if p.is_dir()):
        demand = profile_daily(dir_path)

    weathers = [profile_weather(p) for p in sorted(samples.glob("meteo*.json"))]
    if demand is not None:
        for weather in weathers:
            profile_join(demand, weather)


if __name__ == "__main__":
    main()
