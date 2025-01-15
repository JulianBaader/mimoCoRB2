from mimocorb2.function_templates import Exporter

import numpy as np
import multiprocessing
import time
import os
import matplotlib.pyplot as plt

def drain(*mimo_args):
    exporter = Exporter(mimo_args)
    generator = exporter()
    while True:
        data, metadata = next(generator)
        if data is None:
            break
        
def histogram(*mimo_args):
    exporter = Exporter(mimo_args)
    
    # Get info from the buffer
    name = exporter.reader.buffer_info['name']
    data_example = exporter.reader.buffer_info['data_example']
    available_channels = data_example.dtype.names
    
    if data_example.size != 1:
        raise ValueError('histogram exporter only supports data_length = 1')
    run_directory = exporter.config['run_directory']
    update_interval = exporter.config.get('update_interval', 1)
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
        p = multiprocessing.Process(target=sub_histogram, args=(files, bins, update_interval, name))
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
        
def sub_histogram(files, bins, update_interval, name):
    channels = list(files.keys())
    fig = plt.figure()
    fig.canvas.manager.set_window_title('Histogram ' + name)
    
    n_plots = len(channels)
    cols = int(np.ceil(np.sqrt(n_plots)))
    rows = int(np.ceil(n_plots / cols))
    axes = fig.subplots(rows, cols)
    axes = axes.flatten()
    
    lines = {ch: ax.plot(bins[ch][:-1], np.load(files[ch]))[0] for ch, ax in zip(channels, axes)}
    
    plt.ion()
    plt.show()
    
    last_update = time.time()
    while True:
        if time.time() - last_update > update_interval:
            for i, ch in enumerate(channels):
                try:
                    lines[ch].set_ydata(np.load(files[ch]))
                except EOFError:
                    continue
                axes[i].relim()
                axes[i].autoscale_view()
            fig.canvas.draw()
        fig.canvas.flush_events()
        time.sleep(1/20)
    
    # TODO why dont i count frames?