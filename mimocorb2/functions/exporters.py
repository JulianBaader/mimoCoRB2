from mimocorb2.function_templates import Exporter

import numpy as np
import time
import os

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
        files[ch] = os.path.join(run_directory, name + '_' + ch + '.hst')
        bins[ch] = np.linspace(bin_config[ch][0], bin_config[ch][1], bin_config[ch][2])
        hists[ch] = np.histogram([], bins=bins[ch])[0]
    
    generator = exporter()
    last_save = time.time()
    
    while True:
        data, metadata = next(generator)
        if data is None:
            break
        for ch in channels:
            hists[ch] += np.histogram(data[ch], bins=bins[ch])[0]
        
        if time.time() - last_save > update_interval:
            for ch in channels:
                np.save(files[ch], hists[ch])
            last_save = time.time()
    for ch in channels:
        np.save(files[ch], hists[ch])