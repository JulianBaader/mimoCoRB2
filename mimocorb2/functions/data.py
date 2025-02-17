from mimocorb2.worker_templates import Exporter, Importer
from mimocorb2.mimo_buffer import mimoBuffer

import numpy as np
import pickle
import time
import os

HEADER = """This is a mimoCoRB file"""


class mimoFile:
    def __init__(
        self,
        filename: str,
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
            self.file = open(self.filename, 'ab')  # Append binary for writing
        elif mode == 'read':
            self.file = open(self.filename, 'rb')  # Read binary for reading
        else:
            raise ValueError("Mode must be 'read' or 'write'")

    @classmethod
    def from_file(cls, filename: str) -> 'mimoFile':
        with open(filename, 'rb') as file:
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
    def from_buffer_object(cls, buffer: mimoBuffer, directory: str) -> 'mimoFile':
        filename = os.path.join(directory, buffer.name + '.mimo')
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
        with open(filename, 'wb') as file:
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


def export(*mimo_args):
    """mimoCoRB Exporter: Export data to a mimo file"""
    exporter = Exporter(mimo_args)

    file = mimoFile.from_buffer_object(exporter.reader.buffer, exporter.config['run_directory'])

    with file:
        for data, metadata in exporter:
            file.write_data(data, metadata)


def simulate_importer(*mimo_args):
    """mimoCoRB Importer: Import data from a mimo file with the timing of the original data"""
    # TODO Think about the fact, that the ordering of events is probably not correct
    # TODO check if the sink is still alive
    importer = Importer(mimo_args)
    filename = importer.config['filename']

    file = mimoFile.from_file(filename)
    if file.data_dtype != importer.writer.buffer.data_example.dtype:
        raise ValueError("Data type mismatch")
    if file.data_length != importer.writer.buffer.data_example.size:
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
                yield None, None
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


def clocked_importer(*mimo_args):
    """mimoCoRB Importer: Import data from a mimo file with a fixed (uniform/poisson) rate"""
    raise NotImplementedError("This function is not yet implemented")
    # TODO a function which just puts in the data and metadata from the file, with a uniform/poisson fixed rate
