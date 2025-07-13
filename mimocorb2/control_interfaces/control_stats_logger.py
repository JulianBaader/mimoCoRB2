import queue
import time
import pandas as pd
from pathlib import Path

THRESHOLDS = [
    (10, 1),  # Save every 1 second for the first 10 seconds
    (60, 10),  # Save every 10 seconds for the first 60 seconds
    (600, 60),  # Save every 60 seconds for the first 600 seconds
    (3600, 600),  # Save every 600 seconds for the first 3600 seconds
]
FINAL_INTERVAL = 3600  # Save every hour after the first 3600 seconds


def get_save_interval(elapsed_time):
    for threshold, interval in THRESHOLDS:
        if elapsed_time < threshold:
            return interval
    return FINAL_INTERVAL


def flatten_dict_keys(d, parent_key=''):
    """Flatten dictionary keys using dot-notation."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict_keys(v, new_key))
        else:
            items.append(new_key)
    return items


def flatten_dict_values(d):
    """Flatten dictionary values using the same order as flatten_dict_keys."""
    values = []
    for v in d.values():
        if isinstance(v, dict):
            values.extend(flatten_dict_values(v))
        else:
            values.append(v)
    return values


def control_stats_logger(command_queue: queue, stats_queue: queue, print_queue: queue, run_dir: Path):
    stats = stats_queue.get()
    keys = flatten_dict_keys(stats)
    df = pd.DataFrame(columns=keys)
    df.to_csv(run_dir / 'stats.csv', index=False)

    def save_stats(stats):
        """Save stats to CSV file."""
        values = flatten_dict_values(stats)
        df = pd.DataFrame([values], columns=keys)
        df.to_csv(run_dir / 'stats.csv', mode='a', header=False, index=False)

    start_time = time.time()
    last_save_time = start_time
    while True:
        stats = stats_queue.get()
        # check once per second if there are no workers
        if stats['total_processes_alive'] == 0:
            break
        time.sleep(1)
        now = time.time()
        elapsed_time = now - start_time
        interval = get_save_interval(elapsed_time)

        if now - last_save_time >= interval:
            last_save_time = now
            save_stats(stats)

    save_stats(stats)
