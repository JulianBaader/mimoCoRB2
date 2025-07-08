import time
from typing import Callable, Generator
from mimocorb2.mimo_worker import BufferIO

DATA = 0
METADATA = 1


# Note: anything that returns a generator must have the yield None, None at the very end, as any code following might not be executed


# TODO failing


class Base:
    def __init__(self, io: BufferIO):
        self.io = io
        # copy attributes from io
        self.read = io.read
        self.write = io.write
        self.observe = io.observe
        self.config = io.config
        self.logger = io.logger
        self.name = io.name
        self.run_dir = io.run_dir
        self.setup_dir = io.setup_dir

        # copy methods from io
        self.shutdown_sinks = io.shutdown_sinks


class Importer(Base):
    """Worker class for importing data from an external generator.

    Attributes
    ----------
    data_example : np.ndarray
        Example data from the buffer.

    Examples
    --------
    >>> def worker(buffer_io: BufferIO):
    ...     importer = Importer(buffer_io)
    ...     data_shape = importer.data_example.shape
    ...     def ufunc():
    ...        for i in range(buffer_io['n_events']):
    ...            data = np.random.normal(size=shape)
    ...            yield data
    ...        yield None
    ...     importer(ufunc)
    """

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup."""
        super().__init__(io)
        self.counter = 0

        if len(self.read) != 0:
            self.fail("Importer must have 0 sources", force_shutdown=True)
        if len(self.write) != 1:
            self.fail("Importer must have 1 sink", force_shutdown=True)
        if len(self.observe) != 0:
            self.fail("Importer must have 0 observes", force_shutdown=True)

        self.data_example = self.io.data_out_examples[0]
        self.metadata_example = self.io.metadata_out_examples[0]

    def __call__(self, ufunc: Callable) -> None:
        """Start the generator and write data to the buffer.

        ufunc must yield data of the same format as the io.data_out_examples[0] and yield None at the end.
        Metadata (counter, timestamp, deadtime) is automatically added to the buffer.

        Parameters
        ----------
        ufunc : Callable
            Generator function that yields data and ends with None
        """
        if not callable(ufunc):
            self.shutdown_sinks()
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
                raise NotImplementedError("Generator failed, depending on the debug this should restart the generator")
                # restart the generator
                generator = ufunc()
                continue
            if data is None:
                self.shutdown_sinks()
                break
            if self.write[0].is_shutdown.value:
                break
            with self.write[0] as (metadata_buffer, data_buffer):
                data_buffer[:] = data
                metadata_buffer['counter'] = self.counter
                metadata_buffer['timestamp'] = timestamp
                time_buffer_ready = time.time()
                metadata_buffer['deadtime'] = (time_buffer_ready - time_data_ready) / (
                    time_buffer_ready - time_last_event
                )
            self.counter += 1
            time_last_event = time.time()
        self.logger.info("Importer finished")


class Exporter(Base):
    """Worker class for exporting data and metadata.

    If provided with an identical sink events will be copied to allow further analysis.

    Attributes
    ----------
    data_example : np.ndarray
        Example data from the buffer.
    metadata_example : np.ndarray
        Example metadata from the buffer.

    Examples
    --------
    >>> def worker(buffer_io: BufferIO):
    ...     exporter = Exporter(buffer_io)
    ...     for data, metadata in exporter:
    ...         print(data, metadata)
    """

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup."""
        super().__init__(io)
        if len(self.read) != 1:
            self.fail("Exporter must have 1 source", force_shutdown=True)
        if len(self.observe) != 0:
            self.fail("Exporter must have 0 observes", force_shutdown=True)

        data_in_example = self.io.data_in_examples[0]
        if len(self.write) != 0:
            for do in self.io.data_out_examples:
                if do.shape != data_in_example.shape:
                    self.fail("Exporter source and sink shapes do not match", force_shutdown=True)
                if do.dtype != data_in_example.dtype:
                    self.fail("Exporter source and sink dtypes do not match", force_shutdown=True)

        self.data_example = self.io.data_in_examples[0]
        self.metadata_example = self.io.metadata_in_examples[0]

    def _iter_without_sinks(self) -> Generator:
        """Yields data and metadata from the buffer until the buffer is shutdown."""
        while True:
            with self.read[0] as (metadata, data):
                if data is None:
                    self.logger.info("Exporter finished")
                    break  # Stop the generator
                yield data, metadata

    def _iter_with_sinks(self) -> Generator:
        """Yields data and metadata from the buffer until the buffer is shutdown."""
        while True:
            with self.read[0] as (metadata, data):
                if data is None:
                    self.shutdown_sinks()
                    self.logger.info("Exporter finished")
                    break  # Stop the generator
                for writer in self.write:
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
        if len(self.write) == 0:
            return self._iter_without_sinks()
        else:
            return self._iter_with_sinks()


class Filter(Base):
    """Worker class for filtering data from one buffer to other buffer(s).

    Analyze data using ufunc(data) and copy or discard data based on the result.

    Attributes
    ----------
    data_example : np.ndarray
        Example data from the buffer.

    Examples
    --------
    >>> def worker(buffer_io: BufferIO):
    ...     filter = Filter(buffer_io)
    ...     min_height = buffer_io['min_height']
    ...     def ufunc(data):
    ...         if np.max(data) > min_height:
    ...             return True
    ...         else:
    ...             return False
    ...     filter(ufunc)
    """

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup."""
        super().__init__(io)
        if len(self.read) != 1:
            self.fail("Filter must have 1 source", force_shutdown=True)
        if len(self.write) == 0:
            self.fail("Filter must have at least 1 sink", force_shutdown=True)
        if len(self.observe) != 0:
            self.fail("Filter must have 0 observes", force_shutdown=True)

        data_in_example = self.io.data_in_examples[0]
        for do in self.io.data_out_examples:
            if do.shape != data_in_example.shape:
                self.fail("Exporter source and sink shapes do not match", force_shutdown=True)
            if do.dtype != data_in_example.dtype:
                self.fail("Exporter source and sink dtypes do not match", force_shutdown=True)

        self.data_example = self.io.data_in_examples[0]

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
            self.shutdown_sinks()
            raise RuntimeError("ufunc not callable")
        self.true_map = [True] * len(self.io.data_out_examples)
        self.logger.info("Filter started")
        while True:
            with self.read[0] as (metadata, data):
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

        self.shutdown_sinks()
        self.logger.info("Filter finished")


class Processor(Base):
    """Worker class for processing data from one buffer to other buffer(s).

    Analyze data using ufunc(data) and send results to the corresponding sinks.

    Examples
    --------
    >>> def worker(buffer_io: BufferIO):
    ...     processor = Processor(buffer_io)
    ...     def ufunc(data):
    ...         return [data + 1, data - 1]
    ...     processor(ufunc)
    """

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup."""
        super().__init__(io)
        if len(self.read) != 1:
            self.fail("Processor must have 1 source", force_shutdown=True)
        if len(self.write) == 0:
            self.fail("Processor must have at least 1 sink", force_shutdown=True)
        if len(self.observe) != 0:
            self.fail("Processor must have 0 observes", force_shutdown=True)

    def __call__(self, ufunc: Callable) -> None:
        """Start the processor and process data using ufunc(data).

        Parameters
        ----------
        ufunc : Callable
            Function which will be called upon the data (io.data_in_examples[0]).
            When the function returns None the data will be discarded.
            Otherwise the function must return a list of results, one for each sink.
            If the result is not None it will be written to the corresponding sink.
        """

        if not callable(ufunc):
            self.shutdown_sinks()
            raise RuntimeError("ufunc not callable")
        self.logger.info("Processor started")
        while True:
            with self.read[0] as (metadata, data):
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
                        with self.write[i] as (metadata_buffer, data_buffer):
                            data_buffer[:] = result
                            metadata_buffer[:] = metadata
        self.shutdown_sinks()
        self.logger.info("Processor finished")


class Observer(Base):
    """Worker class for observing data from a buffer.

    Attributes
    ----------
    data_example : np.ndarray
        Example data from the buffer.

    Examples
    --------
    >>> def worker(buffer_io: BufferIO):
    ...     observer = Observer(buffer_io)
    ...     generator = observer()
    ...     while True:
    ...         data, metadata = next(generator)
    ...         if data is None:
    ...             break
    ...         print(data, metadata)
    ...         time.sleep(1)
    """

    def __init__(self, io: BufferIO) -> None:
        """Checks the setup."""
        super().__init__(io)
        if len(self.read) != 0:
            self.fail("Observer must have 0 source", force_shutdown=True)
        if len(self.write) != 0:
            self.fail("Observer must have 0 sinks", force_shutdown=True)
        if len(self.observe) != 1:
            self.fail("Observer must have 1 observes", force_shutdown=True)

        self.data_example = self.io.data_observe_examples[0]

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
            with self.observe[0] as (metadata, data):
                if data is None:
                    break
                if self.observe[0].is_shutdown.value:
                    break
                yield data, metadata
            # TODO check if buffer is alive
        self.logger.info("Observer finished")
        yield None, None


class IsAlive(Base):
    """Worker class for checking if the buffer is alive.

    This worker does not read or write any data, it only checks if the buffer provided as an observer is still alive.

    Examples
    --------
    >>> def worker(buffer_io: BufferIO):
    ...     is_alive = IsAlive(mimo_args)
    ...     while is_alive():
    ...         print("Buffer is alive")
    ...         time.sleep(1)
    ...     print("Buffer is dead")
    """

    def __init__(self, io: BufferIO) -> None:
        """Initialize the IsAlive worker.

        Parameters
        ----------
        io : BufferIO
            BufferIO object containing the buffer to check.
        """
        super().__init__(io)
        if len(self.read) != 0:
            self.fail("IsAlive must have 0 sources", force_shutdown=True)
        if len(self.write) != 0:
            self.fail("IsAlive must have 0 sinks", force_shutdown=True)
        if len(self.observe) != 1:
            self.fail("IsAlive must have 1 observes", force_shutdown=True)

    def __call__(self) -> bool:
        """Check if the buffer is alive.

        Returns
        -------
        bool
            True if the buffer is alive, False otherwise.
        """
        return self.io.observe[0].is_shutdown.value is False
