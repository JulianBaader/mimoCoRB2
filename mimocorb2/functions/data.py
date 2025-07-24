from mimocorb2 import Exporter, Importer
from mimocorb2.mimo_buffer import mimoBuffer

import numpy as np
import pickle
import time
from pathlib import Path

HEADER = """This is a mimoCoRB file"""


class mimoFile:
    """File handler for mimoCoRB2 data files.

    This class provides methods to read and write data and metadata to a mimo file.
    Mimo files are specifically designed for storing data from mimoCoRB2 buffers.
    The file format is binary and includes a header with metadata about the data types and lengths.

    Attributes
    ----------
    filename : str
        The name of the file to read from or write to.
    data_dtype : np.dtype
        The data type of the data stored in the file.
    data_length : int
        The number of elements in the data array.
    metadata_dtype : np.dtype
        The data type of the metadata stored in the file.
    metadata_length : int
        The number of elements in the metadata array.
    mode : str
        The mode in which the file is opened ('read' or 'write').

    Methods
    -------
    from_file(filename: Path | str) -> 'mimoFile':
        Class method to create a mimoFile instance from an existing file.
    from_buffer_object(buffer: mimoBuffer, run_dir: Path) -> 'mimoFile':
        Class method to create a mimoFile instance from a mimoBuffer object.
    write_data(data: np.ndarray, metadata: np.ndarray) -> None:
        Writes data and metadata to the file.
    read_data() -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        Reads data and metadata from the file in a generator fashion.
    close() -> None:
        Closes the file if it is open.
    __enter__() -> 'mimoFile':
        Context manager entry method to allow usage in a with statement.
    __exit__(exc_type, exc_value, traceback) -> None:
        Context manager exit method to ensure the file is closed properly.

    Example
    -------
    >>> with mimoFile.from_file('data.mimo') as mf:
    >>>     for data, metadata in mf.read_data():
    >>>         print(data, metadata)
    """

    def __init__(
        self,
        filename: Path,
        data_dtype: np.dtype,
        data_length: int,
        metadata_dtype: np.dtype,
        metadata_length: int,
        mode: str,
    ) -> None:
        self.filename = filename
        self.data_dtype = data_dtype
        self.data_length = data_length
        self.metadata_dtype = metadata_dtype
        self.metadata_length = metadata_length
        self.mode = mode

        self._data_byte_length = self.data_dtype.itemsize * self.data_length
        self._metadata_byte_length = self.metadata_dtype.itemsize * self.metadata_length

        # Open file based on mode
        if mode == 'write':
            self.file = self.filename.open('ab')  # Append binary for writing
        elif mode == 'read':
            self.file = self.filename.open('rb')  # Read binary for reading
        else:
            raise ValueError("Mode must be 'read' or 'write'")

    @classmethod
    def from_file(cls, filename: Path | str) -> 'mimoFile':
        filename = Path(filename)
        with filename.open('rb') as file:
            info = pickle.load(file)
        return cls(
            filename,
            info['data_dtype'],
            info['data_length'],
            info['metadata_dtype'],
            info['metadata_length'],
            mode='read',
        )

    @classmethod
    def from_buffer_object(cls, buffer: mimoBuffer, run_dir: Path) -> 'mimoFile':
        filename = run_dir / f'{buffer.name}.mimo'
        data_example = buffer.data_example
        metadata_example = buffer.metadata_example
        info = {
            'version': 1,
            'header': HEADER,
            'data_dtype': data_example.dtype,
            'data_length': data_example.size,
            'metadata_dtype': metadata_example.dtype,
            'metadata_length': metadata_example.size,
        }
        with filename.open('wb') as file:
            pickle.dump(info, file)
        return cls(
            filename, data_example.dtype, data_example.size, metadata_example.dtype, metadata_example.size, mode='write'
        )

    def write_data(self, data: np.ndarray, metadata: np.ndarray) -> None:
        if self.mode != 'write':
            raise RuntimeError("File is not open in write mode")

        data_bytes = data.tobytes()
        metadata_bytes = metadata.tobytes()
        if len(data_bytes) != self._data_byte_length or len(metadata_bytes) != self._metadata_byte_length:
            raise RuntimeError("Number of bytes to be written does not match expected number")

        self.file.write(data_bytes)
        self.file.write(metadata_bytes)

    def read_data(self):
        if self.mode != 'read':
            raise RuntimeError("File is not open in read mode")

        # Read the header only once
        if self.file.tell() == 0:
            pickle.load(self.file)  # Skip the header

        while True:
            data_bytes = self.file.read(self._data_byte_length)
            metadata_bytes = self.file.read(self._metadata_byte_length)
            if not data_bytes or not metadata_bytes:
                yield None, None
                break
            data = np.frombuffer(data_bytes, dtype=self.data_dtype)
            metadata = np.frombuffer(metadata_bytes, dtype=self.metadata_dtype)
            yield data, metadata

    def close(self) -> None:
        """Ensure the file is closed when no longer needed."""
        if not self.file.closed:
            self.file.close()

    def __enter__(self) -> 'mimoFile':
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()


def export(buffer_io):
    """mimoCoRB2 Function: Export data to a mimo file.

    Exports data from a source buffer to a mimo file. This function is useful for saving data streams within the mimoCoRB2 framework.

    Type
    ----
    Exporter

    Buffers
    -------
    sources
        1
    sinks
        Pass through data without modification to all sinks. Must share same dtype as source buffer.
    observes
        0
    """
    exporter = Exporter(buffer_io)

    file = mimoFile.from_buffer_object(exporter.io.read[0].buffer, exporter.run_dir)

    with file:
        for data, metadata in exporter:
            file.write_data(data, metadata)


def simulate_importer(buffer_io):
    """mimoCoRB2 Function: Simulate an Importer by inputting data according to the timestamps in a mimo file.

    Imports data from a mimo file and simulates the Importer behavior by yielding data according to the timestamps in the file.
    This may lead to bunches of data if the timestamps are not ordered correctly.

    Type
    ----
    Importer

    Buffers
    -------
    sources
        0
    sinks
        1 with the same dtype as the data in the mimo file
    observes
        0

    Configs
    -------
    filename : str
        Path to the mimo file to be imported.
    """
    # TODO Think about the fact, that the ordering of events is probably not correct
    # TODO check if the sink is still alive
    importer = Importer(buffer_io)
    filename = importer.config['filename']

    file = mimoFile.from_file(filename)
    if file.data_dtype != importer.data_example.dtype:
        raise ValueError("Data type mismatch")
    if file.data_length != importer.data_example.size:
        raise ValueError("Data length mismatch")
    generator = file.read_data()

    def ufunc():
        data, metadata = next(generator)
        last_event_time = metadata["timestamp"][0]
        last_send_time = time.time()
        yield data
        while True:
            data, metadata = next(generator)
            if data is None or metadata is None:
                print("End of file reached")
                yield None
                break
            event_time = metadata["timestamp"][0]
            time_between_event = event_time - last_event_time
            time_since_last_send = time.time() - last_send_time
            if time_since_last_send < time_between_event:
                time.sleep(time_between_event - time_since_last_send)
            last_event_time = event_time
            last_send_time = time.time()
            yield data

    importer(ufunc)


def clocked_importer(buffer_io):
    """mimoCoRB2 Function: Simulate an Importer by inputting data at a fixed rate.

    Imports data from a mimo file and simulates the Importer behavior by yielding data at a fixed rate.
    This is useful for testing and simulating data streams in a controlled manner.
    Can be used to input uniform or poisson distributed data.

    Type
    ----
    Importer

    Buffers
    -------
    sources
        0
    sinks
        1 with the same dtype as the data in the mimo file
    observes
        0

    Configs
    -------
    rate : float
        Rate at which to yield data in Hz
    distribution : str, optional (default='uniform')
        Distribution to use for generating timestamps. Can be 'uniform' or 'poisson'.
    filename : str
        Path to the mimo file to be imported.
    """

    importer = Importer(buffer_io)
    filename = importer.config['filename']
    rate = importer.config['rate']
    distribution = importer.config.get('distribution', 'uniform')
    if rate <= 0:
        raise ValueError("Rate must be a positive number")

    file = mimoFile.from_file(filename)
    if file.data_dtype != importer.data_example.dtype:
        raise ValueError("Data type mismatch")
    if file.data_length != importer.data_example.size:
        raise ValueError("Data length mismatch")
    generator = file.read_data()

    if distribution == 'uniform':

        def wait():
            time.sleep(1 / rate)
    elif distribution == 'poisson':

        def wait():
            time_between_events = np.random.poisson(1 / rate)
            time.sleep(time_between_events)
    else:
        raise ValueError("Invalid distribution type. Use 'uniform' or 'poisson'.")

    def ufunc():
        while True:
            data, metadata = next(generator)
            if data is None or metadata is None:
                print("End of file reached")
                yield None
                break
            wait()
            yield data

    importer(ufunc)
