"""
Module: daq_ringbuffer

This module implements a ring buffer designed for data acquisition. It is based on the `ringbuffer` module.


Classes
-------
DAQRingBuffer: A ring buffer designed for data acquisition.
TODO

Usage
-----
The module is designed for a arborescence data flow: https://en.wikipedia.org/wiki/Arborescence_(graph_theory)

Examples
--------
Creating a DAQRingBuffer:
    >>> ring_buffer = DAQRingBuffer(name="example", slot_count=10, data_length=1000, [("data", np.float64)])
    
TODO
"""

import ringbuffer
import numpy as np
import yaml




class DAQRingBuffer(ringbuffer.RingBuffer):
    metadata_dtype = np.dtype(
        [
            ("counter", np.longlong),
            ("timestamp", np.float64),
            ("deadtime", np.float64),
        ]
    )

    def __init__(self, name: str, slot_count: int, shape, dtype=float, overwrite=True):  
        self.buffer_information = {
            'name': name,
            'slot_count': slot_count,
            'overwrite': overwrite,
            'example_data': np.zeros(shape=shape, dtype=dtype),
            'example_metadata': np.zeros(shape=1, dtype=self.metadata_dtype),
        }      
        # calculate the sizes in bytes
        self.data_byte_size = self.buffer_information['example_data'].nbytes
        self.metadata_byte_size = self.buffer_information['example_metadata'].nbytes
        
        self.slot_byte_size = self.data_byte_size + self.metadata_byte_size

        # create the ring buffer
        super().__init__(name, self.slot_count, self.slot_byte_size, self.overwrite)