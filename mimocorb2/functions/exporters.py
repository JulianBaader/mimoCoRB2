from mimocorb2.worker_templates import Exporter, IsAlive

import numpy as np
from numpy.lib import recfunctions as rfn
import pandas as pd
import time
import os
import matplotlib.pyplot as plt


def drain(buffer_io):
    """mimoCoRB2 Function: Drain buffer

    Drains all data from the source buffer and does nothing with it.

    Type
    ----
    Exporter

    Buffers
    -------
    sources
        1
    sinks
        0
    observes
        0
    """
    exporter = Exporter(buffer_io)
    for data, metadata in exporter:
        pass


def histogram(buffer_io):
    """mimoCoRB2 Function: Export data as a histogram.

    Saves histograms of the data in the source buffer to npy files in the run_directory for each field in the source buffer.
    The histograms are saved in a directory named "Histograms_<source_buffer_name>".
    The directory contains a file named "info.csv" with the histogram configuration and individual npy files for each channel.
    It is possible to visualize the histograms using the `visualize_histogram` function.

    Type
    ----
    Exporter

    Buffers
    -------
    sources
        1 with data_length = 1
    sinks
        Pass through data without modification to all sinks. Must share same dtype as source buffer.
    observes
        0

    Configs
    -------
    update_interval : int, optional (default=1)
        Interval in seconds to save the histogram data to files.
    bins : dict
        Dictionary where keys are channel names and values are tuples of (min, max, number_of_bins).
        Channels must be present in the source buffer data.

    Examples
    --------
    >>> import numpy as np
    >>> import matplotlib.pyplot as plt
    >>> import pandas as pd
    >>> info_df = pd.read_csv('info.csv')
    >>> bins = {ch: np.linspace(info_df['Min'][i], info_df['Max'][i], info_df['NBins'][i]) for i, ch in enumerate(info_df['Channel'])}
    >>> for ch in info_df['Channel']:
    ...     data = np.load(f'{ch}.npy')
    ...     plt.plot(bins[ch][:-1], data, label=ch)
    >>> plt.legend()
    >>> plt.show()
    """
    exporter = Exporter(buffer_io)

    # Get info from the buffer
    name = buffer_io.buffer_names_in[0]
    data_example = buffer_io.data_in_examples[0]
    available_channels = data_example.dtype.names

    if data_example.size != 1:
        raise ValueError('histogram exporter only supports data_length = 1')

    directory = os.path.join(buffer_io.run_directory, "Histograms_" + name)
    os.makedirs(directory, exist_ok=True)

    # Get config
    update_interval = exporter.config.get('update_interval', 1)
    bin_config = exporter.config['bins']

    requested_channels = bin_config.keys()
    for rch in requested_channels:
        if rch not in available_channels:
            raise ValueError(f"Channel '{rch}' not found in the data")
    channels = requested_channels

    info_df = pd.DataFrame(
        {
            'Channel': channels,
            'Min': [bin_config[ch][0] for ch in channels],
            'Max': [bin_config[ch][1] for ch in channels],
            'NBins': [bin_config[ch][2] for ch in channels],
        }
    )
    info_df.to_csv(os.path.join(directory, 'info.csv'), index=False)

    bins = {}
    hists = {}
    files = {}
    for ch in channels:
        files[ch] = os.path.join(directory, ch + '.npy')
        bins[ch] = np.linspace(bin_config[ch][0], bin_config[ch][1], bin_config[ch][2])
        hists[ch] = np.histogram([], bins=bins[ch])[0]

    def save_hists():
        for ch in channels:
            np.save(files[ch], hists[ch])

    save_hists()

    last_save = time.time()
    for data, metadata in exporter:
        for ch in channels:
            hists[ch] += np.histogram(data[ch], bins=bins[ch])[0]

        if time.time() - last_save > update_interval:
            save_hists()
            last_save = time.time()
    save_hists()


def visualize_histogram(buffer_io):
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
    directory = os.path.join(buffer_io.run_directory, "Histograms_" + name)
    df_file = os.path.join(directory, 'info.csv')
    while not os.path.isfile(df_file):
        if not is_alive():
            return
        time.sleep(0.5)
    info_df = pd.read_csv(df_file)

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

        files[ch] = os.path.join(directory, ch + '.npy')
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


def csv(buffer_io):
    """mimoCoRB2 Function: Save data from the source buffer to a CSV file.

    Saves data from the source buffer to a CSV file in the run_directory.
    Each field in the source buffer is saved as a column in the CSV file.

    Type
    ----
    Exporter

    Buffers
    -------
    sources
        1 with data_length = 1
    sinks
        Pass through data without modification to all sinks. Must share same dtype as source buffer.
    observes
        0

    Configs
    -------
    save_interval : int, optional (default=1)
        Interval in seconds to save the CSV file.
    filename : str, optional (default='exporter_name')
        Name of the CSV file to save the data to. The file will be saved in the run_directory.

    Examples
    --------
    >>> import numpy as np
    >>> import pandas as pd
    >>> print(pd.read_csv('run_directory/exporter_name.csv'))
    """
    exporter = Exporter(buffer_io)
    data_example = exporter.data_example
    metadata_example = exporter.metadata_example

    run_directory = exporter.run_directory
    exporter_name = exporter.name

    config = exporter.config
    save_interval = config.get('save_interval', 1)
    filename = config.get('filename', exporter_name)
    filename = os.path.join(run_directory, f"{filename}.csv")

    if data_example.size != 1:
        raise ValueError('csv exporter only supports data_length = 1')

    header = []
    for dtype_name in metadata_example.dtype.names:
        header.append(dtype_name)

    for dtype_name in data_example.dtype.names:
        header.append(dtype_name)

    # create empty dataframe
    df = pd.DataFrame(columns=header)
    df.to_csv(filename, index=False)
    count = 0

    last_save = time.time()
    count = 0
    for data, metadata in exporter:
        count += 1
        line = np.append(rfn.structured_to_unstructured(metadata), rfn.structured_to_unstructured(data))
        df.loc[count] = line
        if time.time() - last_save > save_interval:
            df.to_csv(filename, index=False, mode='a', header=False)
            last_save = time.time()
            df = pd.DataFrame(columns=header)
            count = 0

    df.to_csv(filename, index=False, mode='a', header=False)
