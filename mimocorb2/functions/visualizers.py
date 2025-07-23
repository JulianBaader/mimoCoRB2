from mimocorb2.worker_templates import IsAlive

import numpy as np
import pandas as pd
import time
import matplotlib.pyplot as plt


def csv(buffer_io):
    """mimoCoRB2 Function: Visualize histograms from the CSV exporter.

    Visualizes histograms of the data in the source buffer using matplotlib.
    The histograms are read from the CSV file saved by the csv exporter.

    Type
    ----
    IsAlive

    Buffers
    -------
    sources
        0
    sinks
        0
    observes
        1 the same as the source buffer of the exporter

    Configs
    -------
    update_interval : int, optional (default=1)
        Interval in seconds to update the histograms.
    histtype : str, optional (default='bar')
        Passed to matplotlib's hist function. Options are 'bar', 'step', or 'stepfilled'.
    bins : dict
        Dictionary where keys are channel names and values are tuples of (min, max, number_of_bins).
        Channels must be present in the source buffer data.
    filename : str, optional (default='buffer_name')
        Name of the CSV file to save the data to. The file will be saved in the run_dir.
    """
    is_alive = IsAlive(buffer_io)
    name = buffer_io.buffer_names_observe[0]
    run_dir = buffer_io.run_dir
    buffer_name = buffer_io.buffer_names_observe[0]
    filename = buffer_io.get('filename', buffer_name)
    filename = run_dir / f"{filename}.csv"

    available_keys = buffer_io.data_observe_examples[0].dtype.names

    # Get config
    update_interval = buffer_io.get('update_interval', 1)
    plot_type = buffer_io.get('plot_type', 'bar')
    bin_config = buffer_io['bins']

    requested_keys = bin_config.keys()
    bins = {}
    for rch in requested_keys:
        if rch not in available_keys:
            print(f"Channel '{rch}' not found in the data")
            continue
        bins[rch] = np.linspace(bin_config[rch][0], bin_config[rch][1], bin_config[rch][2])

    if not bins:
        print("No valid channels found in the data.")
        return

    while True:
        # Wait for the CSV file to be created by the csv exporter
        if not is_alive():
            return
        try:
            df = pd.read_csv(filename)
            break
        except FileNotFoundError:
            time.sleep(0.5)
        except pd.errors.EmptyDataError:
            time.sleep(0.5)

    # Make grid of subplots
    n_channels = len(bins)
    fig = plt.figure()
    fig.canvas.manager.set_window_title('CSV Histogram ' + name)
    cols = int(np.ceil(np.sqrt(n_channels)))
    rows = int(np.ceil(n_channels / cols))
    axes = fig.subplots(rows, cols)

    if n_channels == 1:
        axes = np.array([axes])

    axes = axes.flatten()

    for i, (k, b) in enumerate(bins.items()):
        ax = axes[i]
        ax.hist(df[k].values, bins=b, histtype=plot_type)
        ax.set_title(k)
        ax.set_xlabel('Value')
        ax.set_ylabel('Count')

    fig.tight_layout()
    plt.ion()
    plt.show()

    last_update = time.time()
    while is_alive():
        if time.time() - last_update > update_interval:
            try:
                df = pd.read_csv(filename)
            except (FileNotFoundError, pd.errors.EmptyDataError):
                continue

            for i, (k, b) in enumerate(bins.items()):
                ax = axes[i]
                ax.clear()
                ax.hist(df[k].values, bins=b, histtype=plot_type)
                ax.set_title(k)
                ax.set_xlabel('Value')
                ax.set_ylabel('Count')

            fig.canvas.draw()
            last_update = time.time()

        fig.canvas.flush_events()
        time.sleep(1 / 20)


def histogram(buffer_io):
    """mimoCoRB2 Function: Visualize histograms from the histogram exporter.

    Visualizes histograms of the data in the source buffer using matplotlib.
    The histograms are read from the npy files saved by the histogram exporter.

    Type
    ----
    IsAlive

    Buffers
    -------
    sources
        0
    sinks
        0
    observes
        1 the same as the source buffer of the exporter

    Configs
    -------
    update_interval : int, optional (default=1)
        Interval in seconds to update the histograms.
    plot_type : str, optional (default='line')
        Type of plot to use for the histograms. Options are 'line', 'bar', or 'step'.
    """
    is_alive = IsAlive(buffer_io)
    name = buffer_io.buffer_names_observe[0]
    directory = buffer_io.run_dir / f"Histograms_{name}"
    df_file = directory / 'info.csv'
    while True:
        # Wait for the info.csv file to be created by the histogram exporter
        if not is_alive():
            return
        try:
            info_df = pd.read_csv(df_file)
            break
        except FileNotFoundError:
            time.sleep(0.5)
        except pd.errors.EmptyDataError:
            time.sleep(0.5)

    # Get config
    update_interval = buffer_io.get('update_interval', 1)
    plot_type = buffer_io.get('plot_type', 'line')  # 'line', 'bar', or 'step'

    # Make grid of subplots
    n_channels = len(info_df)
    fig = plt.figure()
    fig.canvas.manager.set_window_title('Histogram ' + name)
    cols = int(np.ceil(np.sqrt(n_channels)))
    rows = int(np.ceil(n_channels / cols))
    axes = fig.subplots(rows, cols)
    if n_channels == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    hist_artists = {}
    files = {}
    for i in range(n_channels):
        ch = info_df['Channel'][i]
        ax = axes[i]
        bins = np.linspace(info_df['Min'][i], info_df['Max'][i], info_df['NBins'][i])

        files[ch] = directory / f"{ch}.npy"
        data = np.load(files[ch])
        if plot_type == 'line':
            (hist_artists[ch],) = ax.plot(bins[:-1], data)
        elif plot_type == 'bar':
            hist_artists[ch] = ax.bar(bins[:-1], data, width=0.8 * np.diff(bins), align='edge')
        elif plot_type == 'step':
            (hist_artists[ch],) = ax.step(bins[:-1], data, where='mid')
        else:
            raise ValueError("plot_type must be 'line', 'bar', or 'step'.")

        ax.set_title(ch)
        ax.set_xlabel('Value')
        ax.set_ylabel('Count')
        ax.set_xlim(bins[0], bins[-1])

    fig.tight_layout()
    plt.ion()
    plt.show()

    last_update = time.time()
    while is_alive():
        if time.time() - last_update > update_interval:
            for i, ch in enumerate(info_df['Channel']):
                try:
                    new_data = np.load(files[ch])
                except (EOFError, ValueError):
                    continue

                if plot_type == 'line' or plot_type == 'step':
                    hist_artists[ch].set_ydata(new_data)
                elif plot_type == 'bar':
                    for rect, height in zip(hist_artists[ch], new_data):
                        rect.set_height(height)

                axes[i].relim()
                axes[i].autoscale_view()

            fig.canvas.draw()
            last_update = time.time()

        fig.canvas.flush_events()
        time.sleep(1 / 20)
