from multiprocessing import Process, shared_memory, Queue
import queue
import numpy as np
import time

import mimo_logger

# TODO decide if SimpleQueue or Queue is better

"""
This file contains the implementation of a ring buffer that can be used to store data.
The buffer can easily be accessed by multiple processes using the Reader, Writer and Observer classes.

### Reading from the buffer ###
to gain full access to a filled slot of the buffer use
with Reader(ring_buffer) as buffer: 

or to get a copy of the data use
reader = Reader(ring_buffer)
data = reader.get_copy()


### Writing to the buffer ###
to gain full access to an empty slot of the buffer use
with Writer(ring_buffer) as buffer:

or to write data to the buffer use
writer = Writer(ring_buffer)
writer.from_data(data)

or to write data from a generator use
writer = Writer(ring_buffer)
writer.from_generator(generator)

### Observing the buffer ###
to get a copy of the data in a filled slot of the buffer use
with Observer(ring_buffer) as data:

or

"""


class RingBuffer:
    """
    A ring buffer that can be used to store data.
    The buffer is divided into slots, each slot has a fixed size.

    Management of the slots is done by two queues: empty_slots and filled_slots.
    empty_slots contains the indices of the slots that are empty and can be written to.
    filled_slots contains the indices of the slots that are filled and can be read from.

    These indizes are used as tokens similar to those used in the railway system.

    The buffer is implemented as a shared memory, so it can be accessed by multiple processes.
    The Queues are used to manage the access to the shared memory.
    """

    def __init__(self, name, slot_count, slot_byte_size, overwrite=True, sleep_time=0.05):
        self.log = mimo_logger.Logger("RingBuffer: " + name)

        # constant_metadata
        self.name = name
        self.slot_count = slot_count
        self.slot_byte_size = slot_byte_size

        self.sleep_time = sleep_time
        self.overwrite = overwrite

        # initialize the buffer as a shared memory
        self.shared_memory_buffer = shared_memory.SharedMemory(create=True, size=self.slot_count * self.slot_byte_size)
        self.buffer = np.ndarray((self.slot_count, self.slot_byte_size), dtype=np.uint8, buffer=self.shared_memory.buf)

        # initialize the queues
        self.empty_slots = Queue(self.slot_count)
        self.filled_slots = Queue(self.slot_count + 1)  # +1 for the flush event

        # initialize the empty slots
        for i in range(slot_count):
            self.empty_slots.put(i)

    def get_read_token(self):
        return self.filled_slots.get()

    def return_read_token(self, token):
        self.empty_slots.put(token)

    def get_write_token(self):
        # if overwriting is allowed, try to immideatly get a new slot (block=False)
        #   if there is no empty slot available (wait for) a filled slot
        # if overwriting is not allowed, wait for an empty slot (block=True)
        try:
            return self.empty_slots.get(block=not self.overwrite)
        except queue.Empty:
            return self.filled_slots.get()

    def return_write_token(self, token):
        self.filled_slots.put(token)

    def __del__(self):
        self.shared_memory.close()
        self.shared_memory.unlink()

    def get_metadata(self):
        return {
            "name": self.name,
            "slot_count": self.slot_count,
            "slot_byte_size": self.slot_byte_size,
            "overwrite": self.overwrite,
            "sleep_time": self.sleep_time,
        }


class Reader:
    def __init__(self, ring_buffer):
        self.ring_buffer = ring_buffer

    def __enter__(self):
        self.token = self.ring_buffer.get_read_token()
        if self.token is None:
            return None
        return self.ring_buffer.buffer[self.token]

    def __exit__(self, exc_type, exc_value, traceback):
        self.ring_buffer.return_read_token(self.token)


class Writer:
    def __init__(self, ring_buffer):
        self.ring_buffer = ring_buffer

    def __enter__(self):
        self.token = self.ring_buffer.get_write_token()
        return self.ring_buffer.buffer[self.token]

    def __exit__(self, exc_type, exc_value, traceback):
        self.ring_buffer.return_write_token(self.token)


class Observer:
    def __init__(self, ring_buffer):
        self.ring_buffer = ring_buffer

    def __enter__(self):
        token = self.ring_buffer.get_read_token()
        data = self.ring_buffer.buffer[token].copy()
        self.ring_buffer.return_read_token(token)
        return data

    def __exit__(self, exc_type, exc_value, traceback):
        pass


if __name__ == "__main__":
    ring_buffer = RingBuffer(name="test", slot_count=10, slot_byte_size=10)

    def producer(ring_buffer):
        for i in range(10):
            with Writer(ring_buffer) as buffer:
                buffer[:] = i
                time.sleep(1)

    def consumer(ring_buffer):
        for i in range(100):
            with Reader(ring_buffer) as buffer:
                print(buffer)

    producers = []
    consumers = []
    for j in range(10):
        producers.append(Process(target=producer, args=(ring_buffer,)))
        consumers.append(Process(target=consumer, args=(ring_buffer,)))

    for p1, p2 in zip(producers, consumers):
        p1.start()
        p2.start()
    for p1, p2 in zip(producers, consumers):
        p1.join()
        p2.join()

    # flush event und jeder consumer schiebt ein flush event wieder zurück
