"""
mimo_buffer.py
==============

Multiple In Multiple Out buffer. A module for managing multiprocessing-safe buffers using shared memory.
This module is designed for high-performance data processing tasks where data must be shared across multiple processes efficiently.


Classes
-------
mimoBuffer
    Implements a ring buffer using shared memory to manage slots containing structured data and metadata.

Interface
    Base class for interacting with the buffer (Reader, Writer, Observer).

Reader
    Provides context management for reading data from the buffer.

Writer
    Provides context management for writing data to the buffer and sending flush events.

Observer
    Provides context management for observing data from the buffer without modifying it.

Examples
--------
Creating and using a buffer for multiprocessing data handling:

>>> import numpy as np
>>> from mimo_buffer import mimoBuffer, Writer, Reader
>>> buffer = mimoBuffer("example", slot_count=4, data_length=10, data_dtype=np.dtype([('value', '<f4')]))
>>> with Writer(buffer) as (data, metadata):
...     data['value'][:] = np.arange(10)
...     metadata['counter'][0] = 1
>>> with Reader(buffer) as (data, metadata):
...     print(data['value'], metadata['counter'])
[0. 1. 2. 3. 4. 5. 6. 7. 8. 9.] [1]
"""

import numpy as np
from multiprocessing import shared_memory, Queue, Value
import ctypes
import logging
import time

logger = logging.getLogger(__name__)


class mimoBuffer:
    """
    A multiprocessing-safe ring buffer with shared memory for data and metadata.

    Parameters
    ----------
    name : str
        Unique name for the buffer.
    slot_count : int
        Number of slots in the buffer.
    data_length : int
        Length of the structured data array in each slot.
    data_dtype : np.dtype
        Data type of the structured data array.

    Attributes
    ----------
    metadata_dtype : np.dtype
        Data type for the metadata array.
    metadata_length : int
        Length of the metadata array.
    slot_byte_size : int
        Total byte size of a single slot (data + metadata).
    buffer : np.ndarray
        Shared memory buffer managed as a 2D array.
    empty_slots : multiprocessing.Queue
        Queue of empty slots available for writing.
    filled_slots : multiprocessing.Queue
        Queue of filled slots available for reading or observing.
    event_count : multiprocessing.Value
        Total number of events (writes) that have occurred.
    total_deadtime : multiprocessing.Value
        Total deadtime of all events.
    paused : multiprocessing.Value
        Indicates whether the buffer is paused.
    paused_count : multiprocessing.Value
        Number of events discarded whilst being paused.
    flush_event_received : multiprocessing.Value
        Indicates whether a flush event has been sent.

    Methods
    -------
    get_stats()
        Retrieve statistics about the buffer's usage.
    access_slot_to_observe(token)
        Access a slot to observe data from.
    access_slot_to_read(token)
        Access a slot to read data from.
    access_slot_to_write(token)
        Access a slot to write data to.
    pause()
        Pause the buffer.
    resume()
        Resume the buffer.
    send_flush_event()
        Send a flush event to notify consumers.
    get_write_token()
        Get a token for writing data to a slot.
    return_write_token(token)
        Return a token after writing data to it.
    get_read_token()
        Get a token for reading data from a slot.
    return_read_token(token)
        Return a token after reading data from it.
    get_observe_token()
        Get a token for observing data from a slot.
    return_observe_token(token)
        Return a token after observing data from it.
    """

    metadata_dtype = np.dtype(
        [
            ("counter", np.longlong),
            ("timestamp", np.float64),
            ("deadtime", np.float64),
        ]
    )
    metadata_length = 1
    metadata_example = np.zeros(shape=metadata_length, dtype=metadata_dtype)
    metadata_byte_size = metadata_example.nbytes

    def __init__(
        self,
        name: str,
        slot_count: int,
        data_length: int,
        data_dtype: np.dtype,  # , overwrite: bool = True
    ) -> None:
        self.name = name
        self.slot_count = slot_count
        self.data_length = data_length
        self.data_dtype = data_dtype
        # self.overwrite = overwrite

        self.data_example = np.zeros(shape=data_length, dtype=data_dtype)
        self.data_byte_size = self.data_example.nbytes

        self.slot_byte_size = self.data_byte_size + self.metadata_byte_size

        # initialize the buffer as a shared memory
        self.shared_memory_buffer = shared_memory.SharedMemory(create=True, size=self.slot_byte_size * self.slot_count)
        self.buffer = np.ndarray(
            shape=(self.slot_count, self.slot_byte_size),
            dtype=np.uint8,
            buffer=self.shared_memory_buffer.buf,
        )

        self.shared_memory_trash = shared_memory.SharedMemory(
            create=True, size=self.slot_byte_size
        )  # for draining data whilst in paused mode
        self.trash = np.ndarray(
            shape=(1, self.slot_byte_size),
            dtype=np.uint8,
            buffer=self.shared_memory_trash.buf,
        )

        # initialize the queues
        self.empty_slots = Queue(self.slot_count)
        self.filled_slots = Queue(self.slot_count + 1)  # +1 for the flush event

        # fill the empty_slots queue
        for i in range(slot_count):
            self.empty_slots.put(i)

        # dynamic attributes
        self.event_count = Value(ctypes.c_ulonglong, 0)
        # self.overwrite_count = Value(ctypes.c_ulong, 0)
        self.flush_event_received = Value(ctypes.c_bool, False)
        self.total_deadtime = Value(ctypes.c_double, 0.0)
        self.paused_count = Value(ctypes.c_ulonglong, 0)
        self.paused = Value(ctypes.c_bool, False)

        self.last_stats_time = time.time()
        self.last_event_count = 0
        self.last_deadtime = 0

    def get_stats(self) -> dict:
        current_time = time.time()
        current_event_count = self.event_count.value
        current_deadtime = self.total_deadtime.value
        stats = {
            "event_count": self.event_count.value,
            "filled_slots": (self.filled_slots.qsize() - 1) / self.slot_count,
            "empty_slots": self.empty_slots.qsize() / self.slot_count,
            "flush_event_received": self.flush_event_received.value,
            "rate": (current_event_count - self.last_event_count) / (current_time - self.last_stats_time),
            "average_deadtime": _divide(
                current_deadtime - self.last_deadtime, current_event_count - self.last_event_count
            ),
            "paused_count": self.paused_count.value,
            "paused": self.paused.value,
        }
        self.last_stats_time = current_time
        self.last_event_count = current_event_count
        self.last_deadtime = current_deadtime
        return stats
    
    def access_slot(self, slot_number: int | None) -> list[np.ndarray, np.ndarray]:
        """Access a slot by its slot number.
        
        Get a slot from the buffer by its slot number and return the metadata and data arrays.
        When slot_number is None, returns the trash slot.
        
        Parameters
        ----------
        slot_number : int | None
            The slot number to access.
        
        Returns
        -------
        list[np.ndarray, np.ndarray]
            The metadata and data arrays of the slot.
        """
        if slot_number is None:
            slot = self.trash[0]
        else:
            slot = self.buffer[slot_number]
        
        metadata = slot[: self.metadata_byte_size].view(self.metadata_dtype)
        data = slot[self.metadata_byte_size :].view(self.data_dtype)
        
        return [metadata, data]
    
    def read(self) -> list[int, np.ndarray, np.ndarray] | list[None, None, None]:
        """Read data from the buffer.
        
        After reading is finished the token needs to be returned by calling return_read_token.
        When the buffer is shut down, returns [None, None, None].
        
        Returns
        -------
        list[int, np.ndarray, np.ndarray] | list[None, None, None]
            The token, metadata and data arrays of the slot.
        """
        token = self.filled_slots.get()
        if token is None:
            return [None, None, None]
        metadata, data = self.access_slot(token)
        return [token, metadata, data]
    
    def return_read_token(self, token: int | None) -> None:
        """Return a token after reading data from it."""
        if token is not None:
            self.empty_slots.put(token)
        else:
            self.filled_slots.put(None)
    
    def write(self) -> list[int, np.ndarray, np.ndarray]:
        """Write data to the buffer.
        
        After writing is finished the token needs to be returned by calling return_write_token.
        
        Returns
        -------
        list[int, np.ndarray, np.ndarray]
            The token, metadata and data arrays of the slot.
        """
        if self.paused.value:
            token = None
        else:
            token = self.empty_slots.get()
        metadata, data = self.access_slot(token)
        return [token, metadata, data]
    
    def return_write_token(self, token: int | None) -> None:
        """Return a token to which data has been written."""
        if token is None:
            with self.paused_count.get_lock():
                self.paused_count.value += 1
            return None

        with self.event_count.get_lock():
            self.event_count.value += 1
        with self.total_deadtime.get_lock():
            self.total_deadtime.value += self.buffer[token][: self.metadata_byte_size].view(self.metadata_dtype)[
                "deadtime"
            ]  # TODO i think this is ugly

        self.filled_slots.put(token)
    
    def observe(self) -> list[int, np.ndarray, np.ndarray] | list[None, None, None]:
        """Observe data from the buffer.
        
        After observing is finished the token needs to be returned by calling return_observe_token.
        When the buffer is shut down, returns [None, None, None].
        
        Returns
        -------
        list[int, np.ndarray, np.ndarray] | list[None, None, None]
            The token, metadata and data arrays of the slot.
        """
        token = self.filled_slots.get()
        if token is None:
            return [None, None, None]
        metadata, data = self.access_slot(token)
        return [token, metadata, data]
    
    def return_observe_token(self, token: int | None) -> None:
        """Return a token after observing data from it."""
        self.filled_slots.put(token)

    def send_flush_event(self) -> None:
        """Send a flush event to the buffer."""
        with self.flush_event_received.get_lock():
            if not self.flush_event_received.value:
                self.flush_event_received.value = True
                self.filled_slots.put(None)    

    def pause(self) -> None:
        self.paused.value = True

    def resume(self) -> None:
        self.paused.value = False

    def __del__(self) -> None:
        self.shared_memory_buffer.close()
        self.shared_memory_buffer.unlink()
        self.shared_memory_trash.close()
        self.shared_memory_trash.unlink()
        logger.info(f"Buffer {self.name} is shut down.")


class Interface:
    def __init__(self, buffer: mimoBuffer) -> None:
        self.buffer = buffer

        self.shutdown_readers = self.buffer.send_flush_event
        self.get_stats = self.buffer.get_stats
        self.name = self.buffer.name
        self.slot_count = self.buffer.slot_count
        self.data_example = self.buffer.data_example
        self.metadata_example = self.buffer.metadata_example


class BufferReader(Interface):
    """
    A context manager for reading data from a mimoBuffer.

    Methods
    -------
    __enter__()
        Get a token and access the slot for reading.
    __exit__(exc_type, exc_value, traceback)
        Return the token after reading.
    """

    def __enter__(self) -> list[np.ndarray, np.ndarray] | list[None, None]:
        self.token, metadata, data = self.buffer.read()
        return [metadata, data]

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.buffer.return_read_token(self.token)


class BufferWriter(Interface):
    """
    A context manager for writing data to a mimoBuffer.

    Methods
    -------
    __enter__()
        Get a token and access the slot for writing.
    __exit__(exc_type, exc_value, traceback)
        Return the token after writing.
    send_flush_event()
        Send a flush event to notify consumers.
    """

    def __enter__(self) -> list[np.ndarray, np.ndarray]:
        self.token, metadata, data = self.buffer.write()
        return [metadata, data]

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.buffer.return_write_token(self.token)

    def send_flush_event(self) -> None:
        self.buffer.send_flush_event()


class BufferObserver(Interface):
    """
    A context manager for observing data in a mimoBuffer.

    Methods
    -------
    __enter__()
        Get a token and access the slot for observation.
    __exit__(exc_type, exc_value, traceback)
        Return the token after observation.
    """

    def __enter__(self) -> list[np.ndarray, np.ndarray] | list[None, None]:
        self.token, metadata, data = self.buffer.observe()
        return [metadata, data]

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.buffer.return_observe_token(self.token)


def _divide(a, b):
    return a / b if b != 0 else 0
