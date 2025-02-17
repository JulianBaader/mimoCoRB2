import logging
import time
import os
import numpy as np
from typing import TypeAlias, Callable, Generator
from mimocorb2.mimo_buffer import BufferReader, BufferWriter, BufferObserver

ArgsAlias: TypeAlias = list[list[BufferReader], list[BufferWriter], list[BufferObserver], dict]

METADATA = 0
DATA = 1


# Note: anything that returns a generator must have the yield None, None at the very end, as any code following might not be executed


class Template:
    """Base class for interactions between buffers."""

    def __init__(self, mimo_args: ArgsAlias) -> None:
        self.sources, self.sinks, self.observes, self.config = mimo_args
        self.name = self.config['name']
        self.debug = self.config['debug']
        self.run_directory = self.config['run_directory']
        self.logger = logging.getLogger(self.name)
        self.errors_directory = os.path.join(self.run_directory, 'errors')

    def fail(
        self,
        msg: str,
        data: np.ndarray | None = None,
        metadata: np.ndarray | None = None,
        exception: BaseException | None = None,
        force_shutdown: bool = False,
    ):
        if (data is not None) and (metadata is not None):
            np.save(
                os.path.join(
                    self.errors_directory,
                    f"counter_{metadata['counter']}_worker_{self.name}_{self.process_number}.npy",
                ),
                data,
            )

        self.logger.warning(msg)
        if self.debug or force_shutdown:
            for sink in self.sinks:
                sink.buffer.send_flush_event()
            if exception is not None:
                raise exception
            else:
                raise RuntimeError(msg)


class Importer(Template):
    """Worker class for importing data from an external generator.

    Attributes
    ----------
    counter : int
        Counter for the number of events imported
    writer : BufferWriter
        BufferWriter object for writing data to the buffer
        
    Examples
    --------
    >>> def worker(*mimo_args):
    ...     importer = Importer(mimo_args)
    ...     config = importer.config
    ...     data_example = importer.writer.data_example
    ...     buffer_name = importer.writer.name
    ...     def ufunc():
    ...        for i in range(config['n_events']):
    ...            data = np.random.normal(size=data_example.shape)
    ...            yield data
    ...        yield None
    ...     importer(ufunc)    
    """

    def __init__(self, mimo_args: ArgsAlias) -> None:
        """Checks the setup.
        
        Parameters
        ----------
        mimo_args : ArgsAlias
            List of sources, sinks, observes, and config dictionary
        """
        super().__init__(mimo_args)
        self.counter = 0

        if len(self.sources) != 0:
            self.fail("Importer must have 0 sources", force_shutdown=True)
        if len(self.sinks) != 1:
            self.fail("Importer must have 1 sink", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Importer must have 0 observes", force_shutdown=True)

        self.writer = self.sinks[0]

    def __call__(self, ufunc: Callable) -> None:
        """Start the generator and write data to the buffer.
        
        ufunc must yield data of the same format as the Importer.writer.data_example and yield None at the end.
        Metadata (counter, timestamp, deadtime) is automatically added to the buffer.
        
        Parameters
        ----------
        ufunc : Callable
            Generator function that yields data and ends with None    
        """
        if not callable(ufunc):
            self.read_all.send_flush_event()
            raise RuntimeError("ufunc not callable")
        self.logger.info("Importer started")

        time_last_event = time.time()

        generator = ufunc()
        while True:
            try:
                data = next(generator)
                time_data_ready = time.time()
                timestamp = time.time_ns() * 1e-9  # in s as type float64
            except Exception:
                self.fail("Generator failed")
                # restart the generator
                generator = ufunc()
                continue
            if data is None:
                self.writer.buffer.send_flush_event()
                break
            if self.writer.buffer.flush_event_received.value:
                break
            with self.writer as sink:
                sink[DATA][:] = data
                sink[METADATA]['counter'] = self.counter
                sink[METADATA]['timestamp'] = timestamp
                time_buffer_ready = time.time()
                sink[METADATA]['deadtime'] = (time_buffer_ready - time_data_ready) / (
                    time_buffer_ready - time_last_event
                )
            self.counter += 1
            time_last_event = time.time()
        self.logger.info("Importer finished")


class Exporter(Template):
    """Worker class for exporting data and metadata.
    
    Attributes
    ----------
    reader : BufferReader
        BufferReader object for reading data from the buffer

    Examples
    --------
    >>> def worker(*mimo_args):
    ...     exporter = Exporter(mimo_args)
    ...     data_example = exporter.reader.data_example
    ...     buffer_name = exporter.reader.name
    ...     for data, metadata in exporter:
    ...         print(data, metadata)
    """

    def __init__(self, mimo_args: ArgsAlias) -> None:
        """Checks the setup.
        
        Parameters
        ----------
        mimo_args : ArgsAlias
            List of sources, sinks, observes, and config dictionary
        """
        super().__init__(mimo_args)

        if len(self.sources) != 1:
            self.fail("Exporter must have 1 source", force_shutdown=True)
        if len(self.sinks) != 0:
            self.fail("Exporter must have 0 sinks", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Exporter must have 0 observes", force_shutdown=True)

        self.reader = self.sources[0]
        
    def __iter__(self) -> Generator:
        """Yields data and metadata from the buffer until the buffer is shutdown."""
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    self.logger.info("Exporter finished")
                    break  # Stop the generator
                yield data, metadata


class Filter(Template):
    """Worker class for filtering data from one buffer to other buffer(s).

    Analyze data using ufunc(data) and copy or discard data based on the result.
    
    Attributes
    ----------
    reader : BufferReader
        BufferReader object for reading data from the buffer
    writers : list[BufferWriter]
        List of BufferWriter objects for writing data to the buffers
        
    Examples
    --------
    >>> def worker(*mimo_args):
    ...     filter = Filter(mimo_args)
    ...     min_height = filter.config['min_height']
    ...     def ufunc(data):
    ...         if np.max(data) > min_height:
    ...             return True
    ...         else:
    ...             return False
    ...     filter(ufunc)
    """

    def __init__(self, mimo_args: ArgsAlias) -> None:
        """Checks the setup.
        
        Check that the number of sources, sinks, and observes are correct.
        Check that the source and sink shapes and dtypes match.
        """
        super().__init__(mimo_args)

        if len(self.sources) != 1:
            self.fail("Filter must have 1 source", force_shutdown=True)
        if len(self.sinks) == 0:
            self.fail("Filter must have at least 1 sink", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Filter must have 0 observes", force_shutdown=True)

        self.reader = self.sources[0]
        source_data_shape = self.reader.buffer.data_example.shape
        source_data_dtype = self.reader.buffer.data_example.dtype
        for writer in self.sinks:
            data_example = writer.buffer.data_example
            if data_example.shape != source_data_shape:
                self.fail("Filter source and sink shapes do not match", force_shutdown=True)
            if data_example.dtype != source_data_dtype:
                self.fail("Filter source and sink dtypes do not match", force_shutdown=True)
        self.writers = self.sinks

    def __call__(self, ufunc) -> None:
        """Start the filter and copy or discard data based on the result of ufunc(data).
        
        Parameters
        ----------
        ufunc : Callable
            Function which will be called upon the data (Filter.reader.data_example).
            The function can return:
                bool
                    True: copy data to every sink
                    False: discard data
                list[bool] (mapping to the sinks)
                    True: copy data to the corresponding sink
                    False: dont copy data to the corresponding sink
        """
        if not callable(ufunc):
            self.read_all.send_flush_event()
            raise RuntimeError("ufunc not callable")
        self.true_map = [True] * len(self.sinks)
        self.logger.info("Filter started")
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                try:
                    result = ufunc(data)
                except Exception:
                    self.fail("ufunc failed")
                    continue
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
    """Worker class for processing data from one buffer to other buffer(s).

    Attributes
    ----------
    reader : BufferReader
        BufferReader object for reading data from the buffer
    writers : list[BufferWriter]
        List of BufferWriter objects for writing data to the buffers
        
    Examples
    --------
    >>> def worker(*mimo_args):
    ...     processor = Processor(mimo_args)
    ...     def ufunc(data):
    ...         return [data + 1, data - 1]
    ...     processor(ufunc)
    """

    def __init__(self, mimo_args: ArgsAlias) -> None:
        """Checks the setup.
        
        Parameters
        ----------
        mimo_args : ArgsAlias
            List of sources, sinks, observes, and config dictionary
        """
        super().__init__(mimo_args)

        if len(self.sources) != 1:
            self.fail("Processor must have 1 source", force_shutdown=True)
        if len(self.sinks) == 0:
            self.fail("Processor must have at least 1 sink", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Processor must have 0 observes", force_shutdown=True)

        self.reader = self.sources[0]
        self.writers = self.sinks

    def __call__(self, ufunc: Callable) -> None:
        """Start the processor and process data using ufunc(data).
        
        Parameters
        ----------
        ufunc : Callable
            Function which will be called upon the data (Processor.reader.data_example).
            When the function returns None the data will be discarded.
            Otherwise the function must return a list of results, one for each sink.
            If the result is not None it will be written to the corresponding sink.
        """
            
        if not callable(ufunc):
            self.read_all.send_flush_event()
            raise RuntimeError("ufunc not callable")
        self.logger.info("Processor started")
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                try:
                    results = ufunc(data)  # TODO this should be a try?
                except Exception:
                    self.fail("ufunc failed")
                if results is None:
                    continue
                for i, result in enumerate(results):
                    if result is not None:
                        with self.writers[i] as sink:
                            sink[DATA][:] = result
                            sink[METADATA][:] = metadata
        for writer in self.writers:
            writer.buffer.send_flush_event()
        self.logger.info("Processor finished")


class Observer(Template):
    """Worker class for observing data from a buffer.
    
    Attributes
    ----------
    observer : BufferObserver
        BufferObserver object for observing data from the buffer
        
    Examples
    --------
    >>> def worker(*mimo_args):
    ...     observer = Observer(mimo_args)
    ...     generator = observer()
    ...     while True:
    ...         data, metadata = next(generator)
    ...         if data is None:
    ...             break
    ...         print(data, metadata)
    ...         time.sleep(1)
    """
    def __init__(self, mimo_args: ArgsAlias) -> None:
        """Checks the setup.
        
        Parameters
        ----------
        mimo_args : ArgsAlias
            List of sources, sinks, observes, and config dictionary
        """
        super().__init__(mimo_args)

        if len(self.sources) != 0:
            self.fail("Observer must have 0 source", force_shutdown=True)
        if len(self.sinks) != 0:
            self.fail("Observer must have 0 sinks", force_shutdown=True)
        if len(self.observes) != 1:
            self.fail("Observer must have 1 observes", force_shutdown=True)
        self.observer = self.observes[0]

    def __call__(self) -> Generator:
        """Start the observer and yield data and metadata.
        
        Yields data and metadata from the buffer until the buffer is shutdown.
        
        Yields
        ------
        data : np.ndarray, None
            Data from the buffer
        metadata : np.ndarray, None
            Metadata from the buffer
        """
        while True:
            with self.observer as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                yield data, metadata
            if self.observer.buffer.flush_event_received.value:
                break
        self.logger.info("Observer finished")
        yield None, None


class Monitor(Template):
    """Worker Class for Monitoring data transfered between two identical Buffers.
    
    If no sink is provided, the Monitor will act as an Exporter.
    
    Attributes
    ----------
    reader : BufferReader
        BufferReader object for reading data from the buffer
    writer : BufferWriter
        BufferWriter object for writing data to the buffer
    """
    def __init__(self, mimo_args: ArgsAlias) -> None:
        """Checks the setup."""
        super().__init__(mimo_args)

        if len(self.sources) != 1:
            self.fail("Monitor must have 1 source", force_shutdown=True)
        if len(self.sinks) not in [0,1]:
            self.fail("Monitor must have 0 or 1 sink", force_shutdown=True)
        if len(self.observes) != 0:
            self.fail("Monitor must have 0 observes", force_shutdown=True)
            
        self.reader = self.sources[0]
        data_example_in = self.reader.data_example
        self.writer = None
        if len(self.sinks) != 0:
            self.writer = self.sinks[0]
            data_example_out = self.writer.data_example
            
            if data_example_in.shape != data_example_out.shape:
                self.fail("Monitor source and sink shapes do not match", force_shutdown=True)
            if data_example_in.dtype != data_example_out.dtype:
                self.fail("Monitor source and sink dtypes do not match", force_shutdown=True)
            
    def _monitor(self) -> Generator:
        assert self.writer is not None
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                with self.writer as sink:
                    sink[DATA][:] = data
                    sink[METADATA][:] = metadata
                yield data, metadata
                
        self.writer.buffer.send_flush_event()
        self.logger.info("Monitor finished")
        yield None, None
        
    def _exporter(self) -> Generator:
        while True:
            with self.reader as source:
                data = source[DATA]
                metadata = source[METADATA]
                if data is None:
                    break
                yield data, metadata
        self.logger.info("Monitor finished")
        yield None, None
        
    def __call__(self) -> Generator:
        """Start the monitor and yield data and metadata.
        
        Yields data and metadata from the buffer until the buffer is shutdown.
        
        Yields
        ------
        data : np.ndarray, None
            Data from the buffer
        metadata : np.ndarray, None
            Metadata from the buffer
        """
        if self.writer is not None:
            self.logger.info("Starting Monitor as Monitor")
            return self._monitor()
        else:
            self.logger.info("Starting Monitor as Exporter")
            return self._exporter()
        
    