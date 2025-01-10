import numpy as np

from mimocorb2.function_templates import Importer, Filter, Processor, Exporter
import time

import multiprocessing as mp

DATA = 0
METADATA = 1

# TODO importer etc need more information, for example the shape of the buffer


def simulate_osc(*mimo_args):
    importer = Importer(mimo_args)
    rng = np.random.default_rng(seed=abs(hash(mp.current_process().name)))

    def ufunc():
        for i in range(50000):
            arr = np.linspace(0, 10, 100)
            yield np.sin(arr + i) * rng.normal(1, 0.1)
            time.sleep(np.random.poisson(1/1000))
        yield None

    importer.set_ufunc(ufunc)
    importer()


def filter_data(*mimo_args):
    filter = Filter(mimo_args)

    def ufunc(data):
        if np.max(data['ch1']) > 0.5:
            return True
        else:
            return False

    filter.set_ufunc(ufunc)
    filter()


def calculate_pulse_heights(*mimo_args):
    processor = Processor(mimo_args)
    example = processor.sinks[0].buffer.data_example

    def ufunc(data):
        example['pulse_height'] = np.max(data['ch1'])
        return [example]

    processor.set_ufunc(ufunc)
    processor()


def print_pulse_heights(*mimo_args):
    exporter = Exporter(mimo_args)
    gen = exporter()
    while True:
        data, metadata = next(gen)
        if data is None:
            break
        # print(f"Pulse height: {data['pulse_height']}")
