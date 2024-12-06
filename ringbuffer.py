from multiprocessing import Process, shared_memory, Queue, Value
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
        self.buffer = np.ndarray(
            (self.slot_count, self.slot_byte_size), dtype=np.uint8, buffer=self.shared_memory_buffer.buf
        )

        # initialize a flag for shutdown
        self.received_flush_event = Value('b', False)

        # initialize the queues
        self.empty_slots = Queue(self.slot_count)
        self.filled_slots = Queue(self.slot_count + 1)  # +1 for the flush event

        # initialize the empty slots
        for i in range(slot_count):
            self.empty_slots.put(i)

    def send_flush_event(self):
        self.filled_slots.put(None)

    def get_read_token(self):
        return self.filled_slots.get()

    def return_read_token(self, token):
        if token is not None:
            self.empty_slots.put(token)
        else:
            self.filled_slots.put(None)

    def get_write_token(self):
        # if overwriting is allowed, try to immideatly get a new slot (block=False)
        #   if there is no empty slot available try to immideatly get a filled slot nowait
        #   if there is no filled slot available, wait for an empty slot
        # if overwriting is not allowed, wait for an empty slot (block=True)
        try:
            return self.empty_slots.get(block=(not self.overwrite))
        except queue.Empty:
            # this can only happen if overwrite is True
            try:
                token = (
                    self.filled_slots.get_nowait()
                )  # If all slots are being read, this queue will be empty, wait for a slot to be emptied
                if token is None:  # never overwrite a flush event
                    return self.empty_slots.get()
                return token
            except queue.Empty:
                return self.empty_slots.get()

    def return_write_token(self, token):
        self.filled_slots.put(token)

    def __del__(self):
        self.shared_memory_buffer.close()
        self.shared_memory_buffer.unlink()

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


# class Observer:
#     def __init__(self, ring_buffer):
#         self.ring_buffer = ring_buffer

#     def __enter__(self):
#         token = self.ring_buffer.get_read_token()
#         if token is None:
#             data = None
#         else:
#             data = self.ring_buffer.buffer[token].copy()
#         self.ring_buffer.return_read_token(token)
#         return data

#     def __exit__(self, exc_type, exc_value, traceback):
#         pass


if __name__ == "__main__":
    # Number of Consumers and Producers
    CONSUMER_COUNT = 5
    PRODUCER_COUNT = 5

    # Number of events each producer produces
    EVENT_COUNT = 256

    # Maximum average rate of the consumers and producers
    CONSUMER_RATE = 1000
    PRODUCER_RATE = 1000

    ring_buffer = RingBuffer(name="test", slot_count=10, slot_byte_size=10, overwrite=True)

    def producer(ring_buffer):
        for i in range(EVENT_COUNT):
            with Writer(ring_buffer) as buffer:
                buffer[:] = i % 256
                time.sleep(-np.log(np.random.rand()) / PRODUCER_RATE)

    def consumer(ring_buffer):
        while True:
            with Reader(ring_buffer) as buffer:
                if buffer is None:
                    break
                print(buffer)
                time.sleep(1 / CONSUMER_RATE)

    producers = []
    consumers = []
    for i in range(PRODUCER_COUNT):
        producers.append(Process(target=producer, args=(ring_buffer,)))
    for i in range(CONSUMER_COUNT):
        consumers.append(Process(target=consumer, args=(ring_buffer,)))

    for c in consumers:
        c.start()
    for p in producers:
        p.start()

    for p in producers:
        p.join()
    print("producers finished")
    ring_buffer.send_flush_event()
    for c in consumers:
        c.join()
