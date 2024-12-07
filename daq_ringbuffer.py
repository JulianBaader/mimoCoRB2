import ringbuffer
import numpy as np

"""
This module builds upon the ringbuffer module and is an api designed for data acquisition purposes.
"""

class DAQRingBuffer(ringbuffer.RingBuffer):
    def __init__(self, name, slot_count, batch_count, data_length, dtype, overwrite=True):
        # create dtype for the buffer and metadata
        self.data_dtype = np.dtype(dtype)
        self.metadata_dtype = np.dtype([
            ("counter", np.longlong),
            ("timestamp", np.float64),
            ("deadtime", np.float64),
        ])
        
        # load dimensions
        self.slot_count = slot_count
        self.batch_count = batch_count
        self.data_length = data_length
        
        if self.batch_count == 1:
            self.get_data = self._get_data
            self.put_data = self._put_data
        
        # calculate the sizes in bytes
        self.data_byte_size = self.data_length * self.data_dtype.itemsize
        self.metadata_byte_size = 1 * self.metadata_dtype.itemsize
        
        self.batch_byte_size = self.data_byte_size + self.metadata_byte_size
        
        self.slot_byte_size = self.batch_byte_size * self.batch_count
        
    
        
        # create the ring buffer
        super().__init__(name, self.slot_count, self.slot_byte_size, overwrite)
        
        self.buffer = self.buffer.reshape((self.slot_count, self.batch_count, self.data_byte_size + self.metadata_byte_size))