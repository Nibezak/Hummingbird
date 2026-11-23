import sqlite3
import datetime

conn = sqlite3.connect(r'c:\projects\btc-5m-recorder\btc_5m_data.db')
cursor = conn.cursor()

# Get min and max cycle start_time and cycle_id
cursor.execute('''
    SELECT COUNT(*), MIN(cycle_id), MAX(cycle_id), MIN(start_time), MAX(start_time)
    FROM cycles
''')
cycle_count, min_cid, max_cid, min_start, max_start = cursor.fetchone()

# Get snapshot count and timestamp range
cursor.execute('''
    SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
    FROM snapshots
''')
snap_count, min_snap_ts, max_snap_ts = cursor.fetchone()

# Also check latest snapshot recorded_at
cursor.execute('SELECT recorded_at FROM snapshots ORDER BY id DESC LIMIT 1')
latest_snap_iso = cursor.fetchone()[0]

cursor.execute('SELECT recorded_at FROM snapshots ORDER BY id ASC LIMIT 1')
first_snap_iso = cursor.fetchone()[0]

# Parse timestamps
# min_start is usually ISO string 'YYYY-MM-DDTHH:MM:SS+00:00'
dt_start = datetime.datetime.fromisoformat(min_start.replace('Z', '+00:00'))

# For end, we can take max_cid + 300 or latest_snap_iso or max_snap_ts
dt_end = datetime.datetime.fromtimestamp(max_cid + 300, tz=datetime.timezone.utc)
dt_now = datetime.datetime.now(datetime.timezone.utc)

total_seconds_cycles = (dt_end - dt_start).total_seconds()
total_hours_cycles = total_seconds_cycles / 3600.0

dt_first_snap = datetime.datetime.fromtimestamp(min_snap_ts, tz=datetime.timezone.utc)
dt_last_snap = datetime.datetime.fromtimestamp(max_snap_ts, tz=datetime.timezone.utc)
total_seconds_snaps = (dt_last_snap - dt_first_snap).total_seconds()
total_hours_snaps = total_seconds_snaps / 3600.0

print(f"Cycles Start: {min_start} (Cycle {min_cid})")
print(f"Cycles End: {max_start} (Cycle {max_cid})")
print(f"Total Cycles: {cycle_count}")
print(f"Total Hours (Cycle Span): {total_hours_cycles:.2f} hours ({total_hours_cycles / 24:.2f} days)")
print(f"First Snapshot: {first_snap_iso} ({min_snap_ts})")
print(f"Latest Snapshot: {latest_snap_iso} ({max_snap_ts})")
print(f"Total Snapshots: {snap_count}")
print(f"Total Hours (Snapshot Span): {total_hours_snaps:.2f} hours ({total_hours_snaps / 24:.2f} days)")

conn.close()
