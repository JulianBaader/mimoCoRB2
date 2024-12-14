"""
Module: ringbuffer

This module implements a shared memory ring buffer for efficient inter-process
communication. It provides a mechanism for multiple producer and consumer
processes to share data in a concurrent environment without excessive locking
or data copying. The core functionality is implemented using Python's
`multiprocessing` library and NumPy.

Classes
-------
1. RingBuffer
    - Manages a fixed-size circular buffer in shared memory.
    - Provides methods for producers and consumers to interact with the buffer.
2. Reader
    - A context manager for safely reading data from a `RingBuffer`.
3. Writer
    - A context manager for safely writing data to a `RingBuffer`.
4. MultiWriter
    - A context manager for synchronized writing to multiple `RingBuffer` instances.
5. Observer
    - A context manager for observing data in a `RingBuffer` without consuming it.

Usage
-----
The module is designed for scenarios where multiple producer and consumer
processes need to share a fixed-size data buffer. Typical use cases include
real-time data acquisition systems, logging frameworks, and streaming data
processing.

Examples
--------
Creating a ring buffer:
    >>> ring_buffer = RingBuffer(name="example", slot_count=10, slot_byte_size=1024)

Writing data:
    >>> with Writer(ring_buffer) as buffer:
    ...     buffer[:] = np.arange(len(buffer))

Reading data:
    >>> with Reader(ring_buffer) as buffer:
    ...     if buffer is not None:
    ...         print(buffer)

Running producers and consumers:
    >>> def producer(ring_buffer):
    ...     for i in range(100):
    ...         with Writer(ring_buffer) as buffer:
    ...             buffer[:] = i
    ...
    >>> def consumer(ring_buffer):
    ...     while True:
    ...         with Reader(ring_buffer) as buffer:
    ...             if buffer is None:
    ...                 break
    ...             print(buffer)
    ...
    >>> from multiprocessing import Process
    >>> producers = [Process(target=producer, args=(ring_buffer,)) for _ in range(2)]
    >>> consumers = [Process(target=consumer, args=(ring_buffer,)) for _ in range(2)]
    >>> for p in producers: p.start()
    >>> for c in consumers: c.start()
    >>> for p in producers: p.join()
    >>> ring_buffer.send_flush_event()
    >>> for c in consumers: c.join()

Notes
-----
- The ring buffer supports optional overwriting when it is full.
- A flush event mechanism is implemented to signal the end of data production.
- Care must be taken to handle process synchronization and exceptions
  when using shared resources.
"""

from multiprocessing import shared_memory, Queue, Value
import queue
import numpy as np
import ctypes


class RingBuffer:
    """
    A shared memory ring buffer implementation for efficient inter-process communication.

    The `RingBuffer` class provides a fixed-size buffer where data can be written and read
    by multiple producer and consumer processes. It uses shared memory for data storage
    and queues for managing read and write tokens.

    Parameters
    ----------
    name : str
        Name of the ring buffer instance (used for identification).
    slot_count : int
        Total number of slots in the ring buffer.
    slot_byte_size : int
        Size of each slot in bytes.
    overwrite : bool, optional
        Whether overwriting is allowed when the buffer is full (default is True).

    Attributes
    ----------
    name : str
        Name of the ring buffer instance.
    slot_count : int
        Total number of slots in the ring buffer.
    slot_byte_size : int
        Size of each slot in bytes.
    overwrite : bool
        Whether overwriting is allowed when the buffer is full.
    event_count : multiprocessing.Value
        Total number of write events that have occurred.
    overwrite_count : multiprocessing.Value
        Number of overwrite events that have occurred.
    flush_event_received : multiprocessing.Value
        Flag indicating if a flush event has been sent.
    shared_memory_buffer : multiprocessing.shared_memory.SharedMemory
        Shared memory object for storing the ring buffer data.
    buffer : numpy.ndarray
        Numpy view of the shared memory buffer.
    empty_slots : multiprocessing.Queue
        Queue managing tokens for empty slots.
    filled_slots : multiprocessing.Queue
        Queue managing tokens for filled slots.

    Methods
    -------
    get_metadata():
        Retrieve current metadata of the ring buffer.
    send_flush_event():
        Send a flush event to indicate that producers are finished.
    get_read_token():
        Retrieve a read token to access data in the buffer.
    return_read_token(token):
        Return a read token after consuming the data.
    get_write_token():
        Retrieve a write token to write data to the buffer.
    return_write_token(token):
        Return a write token after writing data to the buffer.

    Notes
    -----
    - A flush event is used to signal consumers to stop consuming data. This ensures
      graceful shutdown of consumers.
    - When overwriting is enabled, the buffer manages conflicts between producers and
      consumers to prevent deadlocks.

    Examples
    --------
    >>> ring_buffer = RingBuffer(name="test", slot_count=10, slot_byte_size=1024)
    >>> with Writer(ring_buffer) as buffer:
    ...     buffer[:] = np.arange(len(buffer))
    >>> with Reader(ring_buffer) as buffer:
    ...     print(buffer)
    """

    def __init__(self, name: str, slot_count: int, slot_byte_size: int, overwrite: bool = True):
        # constant_metadata
        self.name = name
        self.slot_count = slot_count
        self.slot_byte_size = slot_byte_size
        self.overwrite = overwrite

        # dynamic metadata
        self.event_count = Value(ctypes.c_ulonglong, 0)
        self.overwrite_count = Value(ctypes.c_ulong, 0)
        self.flush_event_received = Value(ctypes.c_bool, False)

        # initialize the buffer as a shared memory
        self.shared_memory_buffer = shared_memory.SharedMemory(create=True, size=self.slot_count * self.slot_byte_size)
        self.buffer = np.ndarray(
            (self.slot_count, self.slot_byte_size), dtype=np.uint8, buffer=self.shared_memory_buffer.buf
        )

        # initialize the queues
        self.empty_slots = Queue(self.slot_count)
        self.filled_slots = Queue(self.slot_count + 1)  # +1 for the flush event

        # fill the empty_slots queue
        for i in range(slot_count):
            self.empty_slots.put(i)

    def get_metadata(self):
        """Retrieve the current metadata of the ring buffer"""
        return {
            "name": self.name,
            "slot_count": self.slot_count,
            "slot_byte_size": self.slot_byte_size,
            "overwrite": self.overwrite,
            "event_count": self.event_count.value,
            "overwrite_count": self.overwrite_count.value,
            "empty_slots": self.empty_slotfs.qsize(),
            "filled_slots": self.filled_slots.qsize(),
        }

    def send_flush_event(self):
        """Send a flush event into the queue"""
        with self.flush_event_received.get_lock():
            if not self.flush_event_received.value:
                self.flush_event_received.value = True
                self.filled_slots.put(None)

    def get_read_token(self):
        """Retrieve a read token from the ring buffer"""
        return self.filled_slots.get()

    def return_read_token(self, token):
        """Return a read token to the ring buffer"""
        if token is not None:
            self.empty_slots.put(token)
        else:
            self.filled_slots.put(None)

    def get_write_token(self):
        """Get a write token from the ring buffer"""

        # if overwriting is not allowed, wait for an empty slot (block=True) -> the exception will never be raised
        # if overwriting is allowed, try to immideatly get a new slot (block=False)
        try:
            return self.empty_slots.get(block=(not self.overwrite))
        except queue.Empty:
            # getting here means overwrite is allowed and there is no empty slot available
            # in this case, check if there is a filled slot available which can be overwritten
            # waiting for a filled slot could lead to a deadlock
            try:
                token = self.filled_slots.get_nowait()

                # do not overwrite the flush event
                if token is None:
                    self.filled_slots.put(None)  # put the flush event back into the queue
                    return self.empty_slots.get()  # wait for an empty slot

                # if the token is not None, it is a filled slot which can be overwritten
                with self.overwrite_count.get_lock():
                    self.overwrite_count.value += 1
                return token

            except queue.Empty:
                # getting here means there is no empty slot and no filled slot available, meaning every slot is either being written to or read from
                # to avoid a deadlock in this case, wait for an empty slot
                return self.empty_slots.get()

    def return_write_token(self, token):
        """Return a write token to the ring buffer"""
        with self.event_count.get_lock():
            self.event_count.value += 1
        self.filled_slots.put(token)

    def __del__(self):
        """Destructor of the ring buffer"""
        # TODO debugging send metadata?
        self.shared_memory_buffer.close()
        self.shared_memory_buffer.unlink()


class Reader:
    """
    Context manager for reading data from a ring buffer.

    The `Reader` class provides a convenient interface for safely retrieving a read token
    and accessing the data in the ring buffer for reading. When the context is exited,
    the read token is automatically returned to the ring buffer.

    Parameters
    ----------
    ring_buffer : RingBuffer
        The ring buffer instance from which data will be read.

    Examples
    --------
    >>> with Reader(ring_buffer) as buffer:
    ...     if buffer is not None:
    ...         print(buffer)
    ...
    """

    def __init__(self, ring_buffer: RingBuffer):
        self.ring_buffer = ring_buffer

    def __enter__(self):
        self.token = self.ring_buffer.get_read_token()
        if self.token is None:
            return None
        return self.ring_buffer.buffer[self.token]

    def __exit__(self, exc_type, exc_value, traceback):
        self.ring_buffer.return_read_token(self.token)


class Writer:
    """
    Context manager for writing data to a ring buffer.

    The `Writer` class provides a convenient interface for safely retrieving a write token
    and accessing the data slot in the ring buffer for writing. When the context is exited,
    the write token is automatically returned to the ring buffer.

    Parameters
    ----------
    ring_buffer : RingBuffer
        The ring buffer instance to which data will be written.

    Examples
    --------
    >>> with Writer(ring_buffer) as buffer:
    ...     buffer[:] = np.arange(len(buffer))
    ...
    """

    def __init__(self, ring_buffer: RingBuffer):
        self.ring_buffer = ring_buffer

    def __enter__(self):
        self.token = self.ring_buffer.get_write_token()
        return self.ring_buffer.buffer[self.token]

    def __exit__(self, exc_type, exc_value, traceback):
        self.ring_buffer.return_write_token(self.token)


class MultiWriter:
    """
    Context manager for writing to multiple ring buffers simultaneously.

    The `MultiWriter` class allows synchronized access to multiple ring buffers for writing.
    It retrieves a write token for each buffer, providing access to their respective data slots.
    When the context is exited, all write tokens are automatically returned to their respective ring buffers.

    Parameters
    ----------
    ring_buffers : list of RingBuffer
        A list of ring buffer instances to which data will be written.

    Examples
    --------
    >>> with MultiWriter([ring_buffer1, ring_buffer2]) as buffers:
    ...     for buffer in buffers:
    ...         buffer[:] = np.arange(len(buffer))
    ...
    """

    def __init__(self, ring_buffers: list[RingBuffer]):
        self.ring_buffers = ring_buffers
        self.number_of_buffers = len(ring_buffers)

    def __enter__(self):
        self.tokens = []
        for rb in self.ring_buffers:
            self.tokens.append(rb.get_write_token())
        return [rb.buffer[token] for rb, token in zip(self.ring_buffers, self.tokens)]

    def __exit__(self, exc_type, exc_value, traceback):
        for rb, token in zip(self.ring_buffers, self.tokens):
            rb.return_write_token(token)


class Observer:
    """
    Context manager for observing data in a ring buffer.

    The `Observer` class allows reading data from a ring buffer without consuming the read token.
    This is useful for monitoring or debugging purposes when the data should not be marked as consumed.

    Parameters
    ----------
    ring_buffer : RingBuffer
        The ring buffer instance from which data will be observed.

    Notes
    -----
    The `Observer` reads the data and returns a copy of it to ensure the buffer is not modified
    during observation. The read token is returned immediately after being acquired.

    Examples
    --------
    >>> with Observer(ring_buffer) as data:
    ...     if data is not None:
    ...         print(data)
    ...
    """

    def __init__(self, ring_buffer: RingBuffer):
        self.ring_buffer = ring_buffer

    def __enter__(self):
        token = self.ring_buffer.get_read_token()
        if token is None:
            data = None
        else:
            data = self.ring_buffer.buffer[token].copy()
        self.ring_buffer.return_write_token(token)
        return data

    def __exit__(self, exc_type, exc_value, traceback):
        pass
