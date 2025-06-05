import numpy as np

from mimocorb2.worker_templates import Importer, Filter, Processor, Exporter
import time

import multiprocessing as mp

DATA = 0
METADATA = 1

# TODO importer etc need more information, for example the shape of the buffer


def simulate_osc(buffer_io):
    importer = Importer(buffer_io)
    rng = np.random.default_rng(seed=abs(hash(mp.current_process().name)))

    def ufunc():
        for i in range(50000):
            arr = np.linspace(0, 10, 100)
            yield np.sin(arr + i) * rng.normal(1, 0.1)
            time.sleep(np.random.poisson(1 / 1000))
        yield None

    importer(ufunc)


def filter_data(buffer_io):
    filter = Filter(buffer_io)

    def ufunc(data):
        # print("hey")
        if np.max(data['ch1']) > 0.5:
            return True
        else:
            return False

    filter(ufunc)


def calculate_pulse_heights(buffer_io):
    processor = Processor(buffer_io)
    example = processor.data_out_example

    def ufunc(data):
        example['pulse_height'] = np.max(data['ch1'])
        return [example]

    processor(ufunc)


def print_pulse_heights(buffer_io):
    exporter = Exporter(buffer_io)
    for data, metadata in exporter:
        print(data['pulse_height'][0])
        pass
