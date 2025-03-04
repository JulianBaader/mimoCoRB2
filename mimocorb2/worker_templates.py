import logging
import time
import os
import numpy as np
from typing import Callable, Generator
from mimocorb2.mimo_worker import BufferIO

DATA = 0
METADATA = 1


# Note: anything that returns a generator must have the yield None, None at the very end, as any code following might not be executed


# TODO failing

class Importer:
    """Worker class for importing data from an external generator.

    Attributes
    ----------
    data_example
    metadata_example
    config

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

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup."""
        self.counter = 0
        self.io = io

        if len(self.io.read) != 0:
            self.fail("Importer must have 0 sources", force_shutdown=True)
        if len(self.io.write) != 1:
            self.fail("Importer must have 1 sink", force_shutdown=True)
        if len(self.io.observe) != 0:
            self.fail("Importer must have 0 observes", force_shutdown=True)
            
        self.data_example = self.io.write[0].data_example
        self.metadata_example = self.io.write[0].metadata_example
        self.name = self.io['name']
        self.config = self.io.config # TODO this should be for every worker class?!?


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
            self.io.shutdown_sinks()
            raise RuntimeError("ufunc not callable")
        self.io.logger.info("Importer started")

        time_last_event = time.time()

        generator = ufunc()
        while True:
            try:
                data = next(generator)
                time_data_ready = time.time()
                timestamp = time.time_ns() * 1e-9  # in s as type float64
            except Exception:
                raise NotImplementedError("Generator failed, depending on the debug this should restart the generator")
                # restart the generator
                generator = ufunc()
                continue
            if data is None:
                self.io.shutdown_sinks()
                break
            if self.io.write[0].is_shutdown.value:
                break
            # TODO test if sink is still active
            with self.io.write[0] as (metadata_buffer, data_buffer):
                data_buffer[:] = data
                metadata_buffer['counter'] = self.counter
                metadata_buffer['timestamp'] = timestamp
                time_buffer_ready = time.time()
                metadata_buffer['deadtime'] = (time_buffer_ready - time_data_ready) / (
                    time_buffer_ready - time_last_event
                )
            self.counter += 1
            time_last_event = time.time()
        self.io.logger.info("Importer finished")


class Exporter:
    """Worker class for exporting data and metadata.

    If provided with an identical sink events will be copied to allow further analysis.

    Attributes
    ----------
    data_example
    metadata_example

    Examples
    --------
    >>> def worker(*mimo_args):
    ...     exporter = Exporter(mimo_args)
    ...     data_example = exporter.reader.data_example
    ...     buffer_name = exporter.reader.name
    ...     for data, metadata in exporter:
    ...         print(data, metadata)
    """

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup."""

        self.io = io
        if len(self.io.read) != 1:
            self.fail("Exporter must have 1 source", force_shutdown=True)
        if len(self.io.observe) != 0:
            self.fail("Exporter must have 0 observes", force_shutdown=True)


        self.data_example = self.io.read[0].data_example
        self.metadata_example = self.io.read[0].metadata_example
        self.name = self.io['name']
        self.config = self.io.config # TODO this should be for every worker class?!?

        if len(self.io.write) != 0:
            for writer in self.io.write:
                data_example_out = writer.data_example
                if data_example_out.shape != self.data_example.shape:
                    self.fail("Exporter source and sink shapes do not match", force_shutdown=True)
                if data_example_out.dtype != self.data_example.dtype:
                    self.fail("Exporter source and sink dtypes do not match", force_shutdown=True)

    def _iter_without_sinks(self) -> Generator:
        """Yields data and metadata from the buffer until the buffer is shutdown."""
        while True:
            with self.io.read[0] as (metadata, data):
                if data is None:
                    self.io.logger.info("Exporter finished")
                    break  # Stop the generator
                yield data, metadata

    def _iter_with_sinks(self) -> Generator:
        """Yields data and metadata from the buffer until the buffer is shutdown."""
        while True:
            with self.io.read[0] as (metadata, data):
                if data is None:
                    self.io.shutdown_sinks()
                    self.io.logger.info("Exporter finished")
                    break  # Stop the generator
                for writer in self.io.write:
                    with writer as (metadata_buffer, data_buffer):
                        data_buffer[:] = data
                        metadata_buffer[:] = metadata
                yield data, metadata

    def __iter__(self) -> Generator:
        """Start the exporter and yield data and metadata.

        Yields data and metadata from the buffer until the buffer is shutdown.

        Yields
        ------
        data : np.ndarray, None
            Data from the buffer
        metadata : np.ndarray, None
            Metadata from the buffer
        """
        if len(self.io.write) == 0:
            return self._iter_without_sinks()
        else:
            return self._iter_with_sinks()


class Filter:
    """Worker class for filtering data from one buffer to other buffer(s).

    Analyze data using ufunc(data) and copy or discard data based on the result.

    Attributes
    ----------
    data_example
    metadata_example
    config

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

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup.

        Check that the number of sources, sinks, and observes are correct.
        Check that the source and sink shapes and dtypes match.
        """
        self.io = io
        if len(self.io.read) != 1:
            self.fail("Filter must have 1 source", force_shutdown=True)
        if len(self.io.write) == 0:
            self.fail("Filter must have at least 1 sink", force_shutdown=True)
        if len(self.io.observe) != 0:
            self.fail("Filter must have 0 observes", force_shutdown=True)

        data_in = self.io.read[0].data_example
        for writer in self.io.write:
            data_out = writer.data_example
            if data_in.shape != data_out.shape:
                self.fail("Filter source and sink shapes do not match", force_shutdown=True)
            if data_in.dtype != data_out.dtype:
                self.fail("Filter source and sink dtypes do not match", force_shutdown=True)

        self.data_example = data_in
        self.metadata_example = self.io.read[0].metadata_example
        self.config = self.io.config # TODO this should be for every worker class?!?
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
            self.io.shutdown_sinks()
            raise RuntimeError("ufunc not callable")
        self.true_map = [True] * len(self.sinks)
        self.io.logger.info("Filter started")
        while True:
            with self.io.read[0] as (metadata, data):
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
                    with self.write[i] as (metadata_buffer, data_buffer):
                        if copy:
                            data_buffer[:] = data
                            metadata_buffer[:] = metadata

        self.io.shutdown_sinks()
        self.io.logger.info("Filter finished")


class Processor:
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

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup.

        Parameters
        ----------
        mimo_args : ArgsAlias
            List of sources, sinks, observes, and config dictionary
        """
        self.io = io
        if len(self.io.read) != 1:
            self.fail("Processor must have 1 source", force_shutdown=True)
        if len(self.io.write) == 0:
            self.fail("Processor must have at least 1 sink", force_shutdown=True)
        if len(self.io.observe) != 0:
            self.fail("Processor must have 0 observes", force_shutdown=True)
            
        self.config = self.io.config # TODO this should be for every worker class?!?
        self.data_example_in = self.io.read[0].data_example
        self.metadata_example_in = self.io.read[0].metadata_example
        
        self.data_examples_out = [writer.data_example for writer in self.io.write]
        self.metadata_examples_out = [writer.metadata_example for writer in self.io.write]
            

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
            self.io.shutdown_sinks()
            raise RuntimeError("ufunc not callable")
        self.io.logger.info("Processor started")
        while True:
            with self.io.read[0] as (metadata, data):
                if data is None:
                    break
                try:
                    results = ufunc(data)
                except Exception:
                    self.fail("ufunc failed")
                if results is None:
                    continue
                for i, result in enumerate(results):
                    if result is not None:
                        with self.io.write[i] as (metadata_buffer, data_buffer):
                            data_buffer[:] = result
                            metadata_buffer[:] = metadata
        self.io.shutdown_sinks()
        self.io.logger.info("Processor finished")


class Observer:
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

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup.

        Parameters
        ----------
        mimo_args : ArgsAlias
            List of sources, sinks, observes, and config dictionary
        """
        self.io = io
        if len(self.io.read) != 0:
            self.fail("Observer must have 0 source", force_shutdown=True)
        if len(self.io.write) != 0:
            self.fail("Observer must have 0 sinks", force_shutdown=True)
        if len(self.io.observe) != 1:
            self.fail("Observer must have 1 observes", force_shutdown=True)
            
        self.data_example = self.io.observe[0].data_example
        self.metadata_example = self.io.observe[0].metadata_example
        self.name = self.io['name']
        self.config = self.io.config # TODO this should be for every worker class?!?

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
            with self.io.observe[0] as (metadata, data):
                if data is None:
                    break
                if self.io.observe[0].is_shutdown.value:
                    break
                yield data, metadata
            # TODO check if buffer is alive
        self.io.logger.info("Observer finished")
        yield None, None
