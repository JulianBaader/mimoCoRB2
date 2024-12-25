import numpy as np
from multiprocessing import shared_memory, Queue, Value
import queue
import ctypes


class mimoBuffer:
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

    def __init__(self, name, slot_count: int, data_length: int, data_dtype: np.dtype, overwrite: bool = True):
        self.name = name
        self.slot_count = slot_count
        self.data_length = data_length
        self.data_dtype = data_dtype
        self.overwrite = overwrite

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

        # initialize the queues
        self.empty_slots = Queue(self.slot_count)
        self.filled_slots = Queue(self.slot_count + 1)  # +1 for the flush event

        # fill the empty_slots queue
        for i in range(slot_count):
            self.empty_slots.put(i)

        # dynamic attributes
        self.event_count = Value(ctypes.c_ulonglong, 0)
        self.overwrite_count = Value(ctypes.c_ulong, 0)
        self.flush_event_received = Value(ctypes.c_bool, False)

    def access_slot(self, token):
        if token is None:
            return None, None
        slot = self.buffer[token]
        metadata = slot[: self.metadata_byte_size].view(self.metadata_dtype)
        data = slot[self.metadata_byte_size :].view(self.data_dtype)
        return data, metadata

    def send_flush_event(self):
        """Send a flush event to the buffer."""
        with self.flush_event_received.get_lock():
            if not self.flush_event_received.value:
                self.flush_event_received.value = True
                self.filled_slots.put(None)

    def get_write_token(self):
        """Get a token to write data to the buffer.

        This method handels overwriting.
        """

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
        """Return a token to which data has been written."""
        with self.event_count.get_lock():
            self.event_count.value += 1
        self.filled_slots.put(token)

    def get_read_token(self):
        """Get a token to read data from the buffer."""
        return self.filled_slots.get()

    def return_read_token(self, token):
        """Return a read token to the ring buffer"""
        if token is not None:
            self.empty_slots.put(token)
        else:
            self.filled_slots.put(None)

    def get_observe_token(self):
        """Get a token to observe data from the buffer."""
        return self.filled_slots.get()

    def return_observe_token(self, token):
        """Return a observe token to the ring buffer"""
        self.filled_slots.put(token)

    def __del__(self):
        self.shared_memory_buffer.close()
        self.shared_memory_buffer.unlink()
        print(f"Buffer {self.name} is shut down.") # TODO Logging


class Reader:
    def __init__(self, buffers: list[mimoBuffer]):
        self.buffers = buffers

    def __enter__(self):
        self.tokens = [buffer.get_read_token() for buffer in self.buffers]
        return [buffer.access_slot(token) for buffer, token in zip(self.buffers, self.tokens)]

    def __exit__(self, exc_type, exc_value, traceback):
        for buffer, token in zip(self.buffers, self.tokens):
            buffer.return_read_token(token)


class Writer:
    def __init__(self, buffers: list[mimoBuffer]):
        self.buffers = buffers

    def __enter__(self):
        self.tokens = [buffer.get_write_token() for buffer in self.buffers]
        return [buffer.access_slot(token) for buffer, token in zip(self.buffers, self.tokens)]

    def __exit__(self, exc_type, exc_value, traceback):
        for buffer, token in zip(self.buffers, self.tokens):
            buffer.return_write_token(token)


class Observer:
    def __init__(self, buffers: list[mimoBuffer]):
        self.buffers = buffers

    def __enter__(self):
        self.tokens = [buffer.get_observe_token() for buffer in self.buffers]
        return [buffer.access_slot(token) for buffer, token in zip(self.buffers, self.tokens)]

    def __exit__(self, exc_type, exc_value, traceback):
        for buffer, token in zip(self.buffers, self.tokens):
            buffer.return_observe_token(token)
