import ringbuffer
import numpy as np

"""
This module builds upon the ringbuffer module and is an api designed for data acquisition purposes.
"""

class DAQRingBuffer(ringbuffer.RingBuffer):
    metadata_dtype = np.dtype([
        ("counter", np.longlong),
        ("timestamp", np.float64),
        ("deadtime", np.float64),
    ])
    def __init__(self, name, slot_count, data_length, dtype, overwrite=True):
        # create dtype for the buffer
        self.data_dtype = np.dtype(dtype)
        
        # load dimensions
        self.slot_count = slot_count
        self.data_length = data_length
        
        # calculate the sizes in bytes
        self.data_byte_size = self.data_length * self.data_dtype.itemsize
        self.metadata_byte_size = 1 * self.metadata_dtype.itemsize
        
        self.slot_byte_size = self.slot_count * (self.data_byte_size + self.metadata_byte_size)
        
    
        
        # create the ring buffer
        super().__init__(name, self.slot_count, self.slot_byte_size, overwrite)
        
        self.buffer = self.buffer.reshape((self.slot_count, self.batch_count, self.data_byte_size + self.metadata_byte_size))
        
class Importer:
    def __init__(self, ringbuffer, ufunc, function_name=None):
        self.ringbuffer = ringbuffer
        self.ufunc = ufunc
        self.function_name = function_name
        if function_name is None:
            self.function_name = ufunc.__name__
        self.data_byte_size = ringbuffer.data_byte_size
        self.metadata_byte_size = ringbuffer.metadata_byte_size

        
    def __call__(self):
        gen = self.ufunc()
        while True:
            with ringbuffer.Writer(self.ringbuffer) as slot:
                try:
                    ret = next(gen)
                except StopIteration:
                    ret is None
                if ret is None:
                    self.ringbuffer.send_flush_event()
                    break
                data, metadata = ret
                if data.nb_bytes != self.data_byte_size or metadata.nb_bytes != self.metadata_byte_size:
                    buffer_metadata = self.ringbuffer.get_metadata()
                    print(f"""Importer to ringbuffer {buffer_metadata['name']} received data or metadata from {self.ufunc.__name__} with the wrong size.
                            Shutting down the buffer and the importer.""")
                    self.ringbuffer.send_flush_event()
                    break
                slot[:self.data_byte_size] = data.view(np.uint8)
                slot[self.data_byte_size:] = metadata.view(np.uint8)

            
class Putter:
    def __init__(self, ringbuffer, function_name):
        self.ringbuffer = ringbuffer
        self.data_byte_size = ringbuffer.data_byte_size
        self.metadata_byte_size = ringbuffer.metadata_byte_size
        
    def __call__(self, data, metadata):
        if data.nb_bytes != self.data_byte_size or metadata.nb_bytes != self.metadata_byte_size:
            buffer_metadata = self.ringbuffer.get_metadata()
            print(f"""Importer to ringbuffer {buffer_metadata['name']} received data or metadata from {self.ufunc.__name__} with the wrong size.
                    Shutting down the buffer and the importer.""")
            self.ringbuffer.send_flush_event()
            return False
        if data is None:
            self.ringbuffer.send_flush_event()
            return False
        with ringbuffer.Writer(self.ringbuffer) as slot:
            slot[:self.data_byte_size] = data.view(np.uint8)
            slot[self.data_byte_size:] = metadata.view(np.uint8)
        return True
            
class Exporter:
    def __init__(self, ringbuffer, name):
        self.ringbuffer = ringbuffer
        self.batch_count = ringbuffer.batch_count
        self.data_byte_size = ringbuffer.data_byte_size
        self.data_dtype = ringbuffer.data_dtype
        self.metadata_dtype = ringbuffer.metadata_dtype
    
    def __call__(self):
        while True:
            with ringbuffer.Reader(self.ringbuffer) as slot:
                if slot is None:
                    self.ringbuffer.send_flush_event()
                    yield None
                    break
                for i in range(self.batch_count):
                    batch = slot[i]
                    data = batch[:self.data_byte_size].view(self.data_dtype)
                    metadata = batch[self.data_byte_size:].view(self.metadata_dtype)
                    yield data, metadata

  
class Processor:
    """
    return of the ufunc(data)
    None -> discard event
    list -> mapping to the output ringbuffers
        None -> dont write to the corresponding output ringbuffer
        numpy strucutred array -> write to the corresponding output ringbuffer
        list of numpy structured arrays -> each array is written into a slot of the corresponding output ringbuffer    
    """
    def __init__(self, input_ringbuffer, output_ringbuffers, ufunc, function_name=None, testing=False):
        self.input_ringbuffer = input_ringbuffer
        self.ouput_ringbuffers = output_ringbuffers
        self.number_of_output_buffers = len(output_ringbuffers)
        self.ufunc = ufunc
        self.function_name=function_name
        if self.function_name is None:
            self.function_name = ufunc.__name__
            
        self.testing = testing # TODO implement testing for all points of failure
        
    def shutdown(self):
        self.input_ringbuffer.send_flush_event()
        for output_ringbuffer in self.output_ringbuffers:
            output_ringbuffer.send_flush_event()
            
    def error(self, message, data):
        metadata = self.input_ringbuffer.get_metadata()
        msg = f"Error in {self.function_name} Proccessing from {metadata['name']}: {message}"
        if self.testing:
            msg += "\n\tShutting down the buffer and its child buffers."
            msg += f"\n\tData: {data}" # TODO saving to npy file would be better
            self.shutdown()
        print(msg)
        
        
    def evaluate(self, data):
        try:
            return_of_ufunc = self.ufunc(data)
        except Exception as e:
            self.error(f"Exception: {e}", data)
            return None
        return return_of_ufunc
    
    def map_ufunc_to_buffers(self, return_of_ufunc, metadata):
        if not isinstance(return_of_ufunc, list) or len(return_of_ufunc) != self.number_of_output_buffers:
            self.error("Output of the processing function is not a list or has the wrong length.", data)
            return 
        
        for data_list, output_ringbuffer in zip(return_of_ufunc, self.output_ringbuffers):
            if data_list is None:
                continue
            if not isinstance(data_list, list):
                data_list = [data_list]
            for data in data_list:
                self.write_to_buffer(data, metadata, output_ringbuffer)
                    
    def write_data_to_buffer(self, data, metadata, output_ringbuffer):
        if data is None:
            return
        if not isinstance(data, np.ndarray) or data.dtype != output_ringbuffer.data_dtype:
            self.error("Output of the processing function is not a numpy array or has the wrong dtype.", data)
            return
        if data.nb_bytes != output_ringbuffer.data_byte_size:
            self.error("Output of the processing function has the wrong size.", data)
            return
        with ringbuffer.Writer(output_ringbuffer) as output_slot:
            output_slot[:self.data_byte_size] = data.view(np.uint8)
            output_slot[self.data_byte_size:] = metadata.view(np.uint8)
        
    
    def __call__(self):
        while True:
            with ringbuffer.Reader(self.input_ringbuffer) as input_slot:
                if input_slot is None:
                    return
                data = input_slot[:self.data_byte_size].view(self.input_ringbuffer.data_dtype)
                metadata = input_slot[self.data_byte_size:].view(self.input_ringbuffer.metadata_dtype)
                
                ret = self.evaluate(data)
                if ret is None:
                    continue
                self.map_to_buffers(ret, metadata)