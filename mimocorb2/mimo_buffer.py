"""
mimo_buffer.py
==============

Multiple In Multiple Out buffer. A module for managing multiprocessing-safe buffers using shared memory.
This module is designed for high-performance data processing tasks where data must be shared across multiple processes efficiently.

The buffer itself is implemented as a shared memory which can be accessed by multiple processes through tokens.
Each token represents a slot in the buffer. Tokens are either stored in the empty_slots queue (the corresponding slot is empty and can be written to) or in the filled_slots queue (the corresponding slot is filled).
The Interfaces Reader, Writer, and Observer provide context management for reading, writing, and observing data in the buffer, respectively.
They also handle the management of tokens, ensuring that data can be safely read or written without conflicts.


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
    mimoBuffer is a class that implements a shared memory buffer for managing data slots with metadata.
    It provides mechanisms for reading, writing, observing, and managing the state of the buffer,
    including pausing, resuming, and sending flush events.

    Attributes
    ----------
    metadata_dtype : np.dtype
        Data type for the metadata associated with each slot.
    metadata_length : int
        Length of the metadata array.
    metadata_example : np.ndarray
        Example metadata array with the specified data type.
    metadata_byte_size : int
        Size in bytes of the metadata example.
    name : str
        The name of the buffer.
    slot_count : int
        The number of slots in the buffer.
    data_length : int
        The length of the data in each slot.
    data_dtype : np.dtype
        The data type of the elements in the buffer.
    data_example : np.ndarray
        An example array with the specified data length and type.
    data_byte_size : int
        The size in bytes of the data example.
    slot_byte_size : int
        The size in bytes of a single slot, including metadata.
    shared_memory_buffer : shared_memory.SharedMemory
        Shared memory buffer for storing data.
    buffer : np.ndarray
        Numpy array representing the shared memory buffer.
    shared_memory_trash : shared_memory.SharedMemory
        Shared memory buffer for draining data in paused mode.
    trash : np.ndarray
        Numpy array representing the shared memory trash buffer.
    empty_slots : Queue
        Queue to manage empty slots in the buffer.
    filled_slots : Queue
        Queue to manage filled slots in the buffer.
    event_count : Value
        Counter for the number of events processed.
    flush_event_received : Value
        Flag indicating if a flush event has been received.
    total_deadtime : Value
        Total dead time in seconds.
    paused_count : Value
        Counter for the number of times the buffer was paused.
    paused : Value
        Flag indicating if the buffer is currently paused.
    last_stats_time : float
        Timestamp of the last statistics update.
    last_event_count : int
        Event count at the last statistics update.
    last_deadtime : float
        Dead time at the last statistics update.

    Methods
    -------
    __init__(name: str, slot_count: int, data_length: int, data_dtype: np.dtype) -> None
        Initialize a MimoBuffer instance with the specified parameters.
    get_stats() -> dict
    _access_slot(slot_number: int | None) -> list[np.ndarray, np.ndarray]
        Access a slot by its slot number and return the metadata and data arrays.
    read() -> list[int, np.ndarray, np.ndarray] | list[None, None, None]
        Read data from the buffer and return the token, metadata, and data arrays.
    return_read_token(token: int | None) -> None
        Return a token after reading data from it.
    write() -> list[int, np.ndarray, np.ndarray]
        Write data to the buffer and return the token, metadata, and data arrays.
    return_write_token(token: int | None) -> None
        Return a token to which data has been written.
    observe() -> list[int, np.ndarray, np.ndarray] | list[None, None, None]
        Observe data from the buffer and return the token, metadata, and data arrays.
    return_observe_token(token: int | None) -> None
        Return a token after observing data from it.
    send_flush_event() -> None
        Send a flush event to the buffer.
    pause() -> None
        Pause the buffer, meaning data written to it will be discarded.
    resume() -> None
        Resume the buffer, meaning data written to it will be accepted again.
    from_setup(name: str, setup: dict) -> "mimoBuffer"
    __del__() -> None
        Destructor method to clean up shared memory resources and log buffer shutdown.
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
        data_dtype: np.dtype,
    ) -> None:
        """
        Initialize a MimoBuffer instance.
        Args:
            name (str): The name of the buffer.
            slot_count (int): The number of slots in the buffer.
            data_length (int): The length of the data in each slot.
            data_dtype (np.dtype): The data type of the elements in the buffer.
        Attributes:
            name (str): The name of the buffer.
            slot_count (int): The number of slots in the buffer.
            data_length (int): The length of the data in each slot.
            data_dtype (np.dtype): The data type of the elements in the buffer.
            data_example (np.ndarray): An example array with the specified data length and type.
            data_byte_size (int): The size in bytes of the data example.
            slot_byte_size (int): The size in bytes of a single slot, including metadata.
            shared_memory_buffer (shared_memory.SharedMemory): Shared memory buffer for storing data.
            buffer (np.ndarray): Numpy array representing the shared memory buffer.
            shared_memory_trash (shared_memory.SharedMemory): Shared memory buffer for draining data in paused mode.
            trash (np.ndarray): Numpy array representing the shared memory trash buffer.
            empty_slots (Queue): Queue to manage empty slots in the buffer.
            filled_slots (Queue): Queue to manage filled slots in the buffer.
            event_count (Value): Counter for the number of events processed.
            flush_event_received (Value): Flag indicating if a flush event has been received.
            total_deadtime (Value): Total dead time in seconds.
            paused_count (Value): Counter for the number of times the buffer was paused.
            paused (Value): Flag indicating if the buffer is currently paused.
            last_stats_time (float): Timestamp of the last statistics update.
            last_event_count (int): Event count at the last statistics update.
            last_deadtime (float): Dead time at the last statistics update.
        """
        logger.info(f"Creating buffer {name} with {slot_count} slots of length {data_length} and dtype {data_dtype}")
        self.name = name
        self.slot_count = slot_count
        self.data_length = data_length
        self.data_dtype = data_dtype

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
        self.flush_event_received = Value(ctypes.c_bool, False)
        self.total_deadtime = Value(ctypes.c_double, 0.0)
        self.paused_count = Value(ctypes.c_ulonglong, 0)
        self.paused = Value(ctypes.c_bool, False)

        self.last_stats_time = time.time()
        self.last_event_count = 0
        self.last_deadtime = 0

    def get_stats(self) -> dict:
        """
        Retrieve statistics about the current state of the buffer.
        Returns:
            dict: A dictionary containing the following statistics:
                - event_count (int): The total number of events processed.
                - filled_slots (float): The ratio of filled slots to total slots in the buffer.
                - empty_slots (float): The ratio of empty slots to total slots in the buffer.
                - flush_event_received (bool): Indicates whether a flush event has been received.
                - rate (float): The rate of events processed per second since the last stats retrieval.
                - average_deadtime (float): The average deadtime per event since the last stats retrieval.
                - paused_count (int): The total number of times the buffer has been paused.
                - paused (bool): Indicates whether the buffer is currently paused.
        """

        current_time = time.time()
        current_event_count = self.event_count.value
        current_deadtime = self.total_deadtime.value
        stats = {
            "event_count": self.event_count.value,
            "filled_slots": self.filled_slots.qsize() / self.slot_count,
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

    def _access_slot(self, slot_number: int | None) -> list[np.ndarray, np.ndarray]:
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
        metadata, data = self._access_slot(token)
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
        metadata, data = self._access_slot(token)
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
            ][0]  # TODO i think this is ugly

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
        metadata, data = self._access_slot(token)
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
        """Pause the buffer, meaning data written to it will be discarded."""
        self.paused.value = True

    def resume(self) -> None:
        """Resume the buffer, meaning data written to it will be accepted again."""
        self.paused.value = False

    @classmethod
    def from_setup(cls, name: str, setup: dict) -> "mimoBuffer":
        """
        Create an instance of mimoBuffer from a setup dictionary.

        Args:
            name (str): The name of the buffer.
            setup (dict): A dictionary containing the buffer configuration.
                Expected keys are:
                    - "slot_count" (int): The number of slots in the buffer.
                    - "data_length" (int): The length of the data in each slot.
                    - "data_dtype" (dict): A dictionary mapping field names to their data types.

        Returns:
            mimoBuffer: An instance of mimoBuffer initialized with the provided setup.
        """
        """Initiate the Buffer from a setup dict"""
        buffer = cls(
            name=name,
            slot_count=setup["slot_count"],
            data_length=setup["data_length"],
            data_dtype=np.dtype([(field_name, dtype) for field_name, dtype in setup["data_dtype"].items()]),
        )
        return buffer

    def __del__(self) -> None:
        """
        Destructor method for the buffer class.
        This method is automatically called when the buffer object is about to be destroyed.
        It ensures that the shared memory resources associated with the buffer are properly
        closed and unlinked to prevent resource leaks. Additionally, it logs a message
        indicating that the buffer has been shut down.
        Actions performed:
        - Closes and unlinks the shared memory buffer.
        - Closes and unlinks the shared memory trash.
        - Logs the shutdown of the buffer with its name.
        """
        self.shared_memory_buffer.close()
        self.shared_memory_buffer.unlink()
        self.shared_memory_trash.close()
        self.shared_memory_trash.unlink()
        logger.info(f"{self.name} is shut down.")


class Interface:
    """
    Base class for interacting with a mimoBuffer.

    Attributes
    ----------
    buffer : mimoBuffer
        The buffer instance being managed.
    shutdown_buffer : callable
        A function to send a flush event to the buffer.
    get_stats : callable
        A function to retrieve buffer statistics.
    name : str
        The name of the buffer.
    slot_count : int
        The number of slots in the buffer.
    data_example : np.ndarray
        Example of the data structure in the buffer.
    metadata_example : np.ndarray
        Example of the metadata structure in the buffer.
    is_shutdown : multiprocessing.Value
        Indicates whether the buffer has been shut down.
    """

    def __init__(self, buffer: mimoBuffer) -> None:
        self.buffer = buffer
        self.shutdown_buffer = self.buffer.send_flush_event
        self.get_stats = self.buffer.get_stats
        self.name = self.buffer.name
        self.slot_count = self.buffer.slot_count
        self.data_example = self.buffer.data_example
        self.metadata_example = self.buffer.metadata_example
        self.is_shutdown = self.buffer.flush_event_received


class BufferReader(Interface):
    """
    A context manager for reading data from a mimoBuffer.

    Methods
    -------
    __enter__()
        Get a token and access the slot for reading.
    __exit__(exc_type, exc_value, traceback)
        Return the token after reading.

    Example
    -------
    >>> reader = BufferReader(buffer)
    >>> with reader as (metadata, data):
    ...    print(metadata, data)
    """

    def __enter__(self) -> list[np.ndarray, np.ndarray] | list[None, None]:
        """
        Acquire reading token and retrieve metadata and data from the buffer.

        Returns
        -------
        list[np.ndarray, np.ndarray] or [None, None]
            Metadata and data arrays from the read slot.
            Returns [None, None] if the buffer has been shut down.
        """
        self.token, metadata, data = self.buffer.read()
        return [metadata, data]

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """
        Release the read token, returning the slot to the buffer.
        """
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

    Example
    -------
    >>> writer = BufferWriter(buffer)
    >>> with writer as (metadata, data):
    ...     data[:] = np.arange(10)
    """

    def __enter__(self) -> list[np.ndarray, np.ndarray]:
        """
        Acquire writing token and retrieve metadata and data from the buffer.

        Returns
        -------
        list[np.ndarray, np.ndarray]
            Metadata and data arrays to which can be written.
        """
        self.token, metadata, data = self.buffer.write()
        return [metadata, data]

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """
        Release the write token, returning the slot to the buffer.
        """
        self.buffer.return_write_token(self.token)

    def send_flush_event(self) -> None:
        """
        Send a flush event to notify consumers that the buffer is shut down.
        """
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

    Example
    -------
    >>> observer = BufferObserver(buffer)
    >>> with observer as (metadata, data):
    ...     print(metadata, data)
    """

    def __enter__(self) -> list[np.ndarray, np.ndarray] | list[None, None]:
        """
        Acquire observation token and retrieve metadata and data from the buffer.

        Returns
        -------
        list[np.ndarray, np.ndarray] or [None, None]
            Metadata and data arrays from the observed slot.
            Returns [None, None] if the buffer has been shut down.
        """
        self.token, metadata, data = self.buffer.observe()
        return [metadata, data]

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """
        Release the observation token, returning the slot to the buffer.
        """
        self.buffer.return_observe_token(self.token)


def _divide(a, b):
    """
    Safely divide two numbers, returning 0 if the denominator is zero.

    Parameters
    ----------
    a : float or int
        Numerator.
    b : float or int
        Denominator.

    Returns
    -------
    float or int
        The result of the division a / b, or 0 if b is zero.
    """
    return a / b if b != 0 else 0
