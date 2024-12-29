import multiprocessing
import logging
import time
import os
import numpy as np

DATA = 0
METADATA = 1

class Template:
    def __init__(self, mimo_args):
        self.sources, self.sinks, self.observes, self.config = mimo_args
        self.function_name = self.config['name']
        self.process_number = self.config['process_number']
        self.debug = self.config['debug']
        self.run_directory = self.config['run_directory']
        
        self.logger = logging.getLogger(f"{self.function_name}_{self.process_number}")
        self.errors_directory = os.path.join(self.run_directory, 'errors')
        
        self.ufunc = None
        
    def set_ufunc(self, ufunc):
        if not callable(ufunc):
            self.sinks.send_flush_event()
            raise RuntimeError("ufunc not callable")
        self.ufunc = ufunc
        
    def fail(self, msg, data=None, metadata=None, exception = None, force_shutdown = False):
        if (data is not None) and (metadata is not None):
            np.save(os.path.join(self.errors_directory, f"counter_{metadata['counter']}_function_{self.function_name}_{self.process_number}.npy"), data)
            
        self.logger.warning(msg)
        if self.debug or force_shutdown:
            for sink in self.sinks:
                sink.buffer.send_flush_event()
            if exception is not None:
                raise exception
            else:
                raise RuntimeError(msg)
            

class Importer(Template):
    def __init__(self, mimo_args):
        super().__init__(mimo_args)
        self.counter = 0
        
        if len(self.sourses) != 0:
            self.fail("Importer must have 0 sources", force_shutdown=True)
        if len(self.sinks) != 1:
            self.fail("Importer must have 1 sink", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Importer must have 0 observes", force_shutdown=True)
            
        self.writer = self.sinks[0]
        self.generator = self.ufunc()
        self.logger.info("Importer ufunc started")
    def __call__(self):
        if self.ufunc is None:
            self.read_all.send_flush_event()
            raise RuntimeError("ufunc not set")
        self.logger.info("Importer started")
        
        generator = self.ufunc()
        while True:
            try:
                data = next(generator)
                t_data_ready = time.time()
                timestamp = time.time_ns() * 1e-9  # in s as type float64
            except Exception as e:
                self.fail("Generator failed")
                # restart the generator
                generator = self.ufunc()
                continue
            if data is None:
                break
            with self.writer as sink:
                sink[DATA][:] = data
                sink[METADATA]['counter'] = self.counter
                sink[METADATA]['timestamp'] = timestamp
                t_buffer_ready = time.time()
                sink[METADATA]['deadtime'] = t_buffer_ready - t_data_ready
            self.counter += 1
        self.sink.buffer.send_flush_event()
        self.logger.info("Importer finished")
        
class Exporter(Template):
    def __int__(self, mimo_args):
        super().__init__(mimo_args)
        
        if len(self.sources) != 1:
            self.fail("Exporter must have 1 source", force_shutdown=True)
        if len(self.sinks) != 0:
            self.fail("Exporter must have 0 sinks", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Exporter must have 0 observes", force_shutdown=True)
            
        self.reader = self.sources[0]
                
    def __call__(self):
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                yield data, metadata
        self.logger.info("Exporter finished")
        
class Filter(Template):
    """
    
    ufunc(data) returns
    bool -> Copy data and metadata to all buffers or discard data
    list[bool] (mapping to sinks) -> copy data and metadata to the corresponding buffers or discard data
    
    """
    def __init__(self, mimo_args):
        super().__init__(mimo_args)
        
        if len(self.sources) != 1:
            self.fail("Filter must have 1 source", force_shutdown=True)
        if len(self.sinks) == 0:
            self.fail("Filter must have at least 1 sink", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Filter must have 0 observes", force_shutdown=True)
            
        self.reader = self.sources[0]
        source_shape = self.reader.buffer.shape
        source_dtype = self.reader.buffer.dtype
        for writer in self.sinks:
            data_example = writer.buffer.data_example
            if data_example.shape != source_shape:
                self.fail("Filter source and sink shapes do not match", force_shutdown=True)
            if data_example.dtype != source_dtype:
                self.fail("Filter source and sink dtypes do not match", force_shutdown=True)
        self.writers = self.sinks
                
    def __call__(self):
        self.true_map = [True] * len(self.sinks)
        self.logger.info("Filter started")
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                result = self.ufunc(data)
                if not result:
                    continue
                if isinstance(result, bool):
                    result = self.true_map
                for i, copy in enumerate(result):
                    with self.writers[i] as sink:
                        if copy:
                            sink[DATA][:] = data
                            sink[METADATA][:] = metadata
                        
        for writer in self.writers:
            writer.buffer.send_flush_event()
        self.logger.info("Filter finished")
        
class Processor(Template):
    """
    
    ufunc(data) returns
    None -> Discard data
    list[data, None] -> if none, dont write to that buffer, if data, write to that buffer
    """
    def __init__(self, mimo_args):
        super().__init__(mimo_args)
        
        if len(self.sources) != 1:
            self.fail("Processor must have 1 source", force_shutdown=True)
        if len(self.sinks) == 1:
            self.fail("Processor must have at least 1 sink", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Processor must have 0 observes", force_shutdown=True)
            
        self.reader = self.sources[0]
        self.writers = self.sinks
        
    def __call__(self):
        self.logger.info("Processor started")
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                result = self.ufunc(data)
                if result is None:
                    continue
                for i, result in enumerate(result):
                    if result is not None:
                        with self.writers[i] as sink:
                            sink[DATA][:] = data
                            sink[METADATA][:] = metadata
        for writer in self.writers:
            writer.buffer.send_flush_event()
        self.logger.info("Processor finished")
        
class Observer(Template):
    def __int__(self, mimo_args):
        super().__init__(mimo_args)
        
        if len(self.sources) != 0:
            self.fail("Observer must have 0 source", force_shutdown=True)
        if len(self.sinks) != 0:
            self.fail("Observer must have 0 sinks", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Observer must have 1 observes", force_shutdown=True)
            
        self.observer = self.observes[0]
                
    def __call__(self):
        while True:
            with self.observer as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                yield data, metadata
        self.logger.info("Exporter finished")
        
