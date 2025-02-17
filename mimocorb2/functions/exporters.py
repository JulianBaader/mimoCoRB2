from mimocorb2.worker_templates import Exporter, Monitor

import numpy as np
from numpy.lib import recfunctions as rfn
import pandas as pd
import multiprocessing
import time
import os
import matplotlib.pyplot as plt


def drain(*mimo_args):
    """mimoCoRB Exporter: drain data from a buffer
    
    Buffers
    -------
    1 source
    0 sink
    0 observe
    """
    exporter = Exporter(mimo_args)
    for data, metadata in exporter:
        pass


def histogram(*mimo_args):
    """mimoCoRB Monitor: Create Histograms of data and optionally visualize them.
    
    Histograms are saved in the run_directory under the name of the source buffer and the channel.
    
    
    Buffers
    -------
    1 source with data_length = 1
    0 or 1 sink depending on whether the data should be through-passed
    0 observe

    Configs
    -------
    update_interval : int, optional (default=1)
        Interval in seconds to update the histograms
    bins : dict
        channel: [start, stop, num_bins]
    visualize : bool, optional (default=False)
        Whether to visualize the histograms in real-time
    plot_type : str, optional (default='bar')
        Type of plot to use for the histograms. Options are 'line', 'bar', or 'step'.
    """
    exporter = Monitor(mimo_args)

    # Get info from the buffer
    name = exporter.reader.name
    data_example = exporter.reader.data_example
    available_channels = data_example.dtype.names

    if data_example.size != 1:
        raise ValueError('histogram exporter only supports data_length = 1')
    run_directory = exporter.config['run_directory']
    update_interval = exporter.config.get('update_interval', 1)
    plot_type = exporter.config.get('plot_type', 'bar')
    bin_config = exporter.config['bins']
    visualize = exporter.config.get('visualize', False)
    requested_channels = bin_config.keys()
    for rch in requested_channels:
        if rch not in available_channels:
            raise ValueError(f"Channel '{rch}' not found in the data")
    channels = requested_channels

    bins = {}
    hists = {}
    files = {}
    # TODO i think this should be removed
    if len(channels) > 1:
        run_directory = os.path.join(run_directory, name)
        os.makedirs(run_directory, exist_ok=True)
    for ch in channels:
        files[ch] = os.path.join(run_directory, name + '_' + ch + '.npy')
        bins[ch] = np.linspace(bin_config[ch][0], bin_config[ch][1], bin_config[ch][2])
        hists[ch] = np.histogram([], bins=bins[ch])[0]

    def save_hists():
        for ch in channels:
            np.save(files[ch], hists[ch])

    save_hists()

    if visualize:
        p = multiprocessing.Process(
            target=sub_histogram, args=(files, bins, update_interval, name, plot_type), daemon=True
        )
        p.start()

    generator = exporter()
    last_save = time.time()

    while True:
        data, metadata = next(generator)
        if data is None:
            break
        for ch in channels:
            hists[ch] += np.histogram(data[ch], bins=bins[ch])[0]

        if time.time() - last_save > update_interval:
            save_hists()
            last_save = time.time()
    save_hists()
    if visualize:
        p.terminate()


def sub_histogram(files, bins, update_interval, name, plot_type):
    channels = list(files.keys())
    fig = plt.figure()
    fig.canvas.manager.set_window_title('Histogram ' + name)

    n_plots = len(channels)
    cols = int(np.ceil(np.sqrt(n_plots)))
    rows = int(np.ceil(n_plots / cols))
    axes = fig.subplots(rows, cols)
    if n_plots == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    hist_artists = {}

    for ch, ax in zip(channels, axes):
        data = np.load(files[ch])
        if plot_type == 'line':
            (hist_artists[ch],) = ax.plot(bins[ch][:-1], data)
        elif plot_type == 'bar':
            hist_artists[ch] = ax.bar(bins[ch][:-1], data, width=0.8 * np.diff(bins[ch]), align='edge')
        elif plot_type == 'step':
            (hist_artists[ch],) = ax.step(bins[ch][:-1], data, where='mid')
        else:
            raise ValueError("plot_type must be 'line', 'bar', or 'step'.")

        ax.set_title(ch)
        ax.set_xlabel('Value')
        ax.set_ylabel('Count')
        ax.set_xlim(bins[ch][0], bins[ch][-1])

    fig.tight_layout()
    plt.ion()
    plt.show()

    last_update = time.time()
    while True:
        if time.time() - last_update > update_interval:
            for i, ch in enumerate(channels):
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
    # TODO why dont i count frames?



def csv(*mimo_args):
    """mimoCoRB Exporter: Save data to a csv file for pandas to read.
    
    File is saved in the run_directory under the name of the source buffer.
    
    Buffers
    -------
    1 source with data_length = 1
    0 sink
    0 observe
    
    Configs
    -------
    save_interval : int, optional (default=1)
        Interval in seconds to save the csv file.
    """
    exporter = Exporter(mimo_args)
    data_example = exporter.reader.data_example
    metadata_example = exporter.reader.metadata_example
    
    config = exporter.config
    save_interval = config.get('save_interval', 1)
    
    if data_example.size != 1:
        raise ValueError('csv exporter only supports data_length = 1')
    
    run_directory = exporter.config['run_directory']
    name = exporter.reader.name
    
    header = []
    for dtype_name in metadata_example.dtype.names:
        header.append(dtype_name)

    for dtype_name in data_example.dtype.names:
        header.append(dtype_name)
        
    # create empty dataframe
    df = pd.DataFrame(columns=header)
    df.to_csv(os.path.join(run_directory, f"{name}.csv"), index=False)
    count = 0

    last_save = time.time()
    count = 0
    for data, metadata in exporter:
        count += 1
        line = np.append(
            rfn.structured_to_unstructured(metadata),
            rfn.structured_to_unstructured(data)
        )
        df.loc[count] = line
        if time.time() - last_save > save_interval:
            df.to_csv(os.path.join(run_directory, f"{name}.csv"), index=False)
            last_save = time.time()
            df = pd.DataFrame(columns=header)
            count = 0
        
    df.to_csv(os.path.join(run_directory, f"{name}.csv"), index=False)
        
