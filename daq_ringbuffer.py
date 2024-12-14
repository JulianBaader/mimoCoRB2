"""
Module: daq_ringbuffer

This module implements a ring buffer designed for data acquisition. It is based on the `ringbuffer` module.
Different classes are implemented to import, process, and export data from the ring buffer.


Classes
-------
DAQRingBuffer: A ring buffer designed for data acquisition.
Importer: A class that imports data from a generator into a `DAQRingBuffer`.
Putter: A class to put data into a `DAQRingBuffer`.
Exporter: A class that exports data from a `DAQRingBuffer`.
Processor: A class that processes data from an input `DAQRingBuffer` and writes it to output `DAQRingBuffer`s.

Usage
-----
The module is designed for a arborescence data flow: https://en.wikipedia.org/wiki/Arborescence_(graph_theory)

Examples
--------
Creating a DAQRingBuffer:
    >>> ring_buffer = DAQRingBuffer(name="example", slot_count=10, data_length=1000, [("data", np.float64)])
    
TODO
"""

import ringbuffer
import numpy as np




class DAQRingBuffer(ringbuffer.RingBuffer):
    metadata_dtype = np.dtype(
        [
            ("counter", np.longlong),
            ("timestamp", np.float64),
            ("deadtime", np.float64),
        ]
    )

    def __init__(self, name: str, slot_count: int, data_length: int, dtype, overwrite=True):
        # create dtype for the buffer
        self.data_dtype = np.dtype(dtype)

        # load dimensions
        self.slot_count = slot_count
        self.data_length = data_length

        # calculate the sizes in bytes
        self.data_byte_size = self.data_length * self.data_dtype.itemsize
        self.metadata_byte_size = 1 * self.metadata_dtype.itemsize
        
        self.slot_byte_size = self.data_byte_size + self.metadata_byte_size

        # create the ring buffer
        super().__init__(name, self.slot_count, self.slot_byte_size, overwrite)
        self.buffer = self.buffer.reshape((self.slot_count, self.slot_byte_size))


class Importer:
    def __init__(self, ringbuffer, ufunc, function_name=None):
        self.ringbuffer = ringbuffer
        self.ufunc = ufunc
        self.function_name = function_name
        if function_name is None:
            self.function_name = ufunc.__name__
        self.data_byte_size = ringbuffer.data_byte_size
        self.metadata_byte_size = ringbuffer.metadata_byte_size

    def __call__(self):
        gen = self.ufunc()
        while True:
            with ringbuffer.Writer(self.ringbuffer) as slot:
                try:
                    ret = next(gen)
                except StopIteration:
                    ret is None
                if ret is None:
                    self.ringbuffer.send_flush_event()
                    break
                data, metadata = ret
                if data.nbytes != self.data_byte_size or metadata.nbytes != self.metadata_byte_size:
                    buffer_metadata = self.ringbuffer.get_metadata()
                    print(f"""Importer to ringbuffer {buffer_metadata['name']} received data or metadata from {self.ufunc.__name__} with the wrong size.
                            Shutting down the buffer and the importer.""")  # TODO more information about the shapes and dtypes
                    self.ringbuffer.send_flush_event()
                    break
                slot[: self.data_byte_size] = data.view(np.uint8)
                slot[self.data_byte_size :] = metadata.view(np.uint8)


class Putter:
    def __init__(self, ringbuffer, function_name):
        self.ringbuffer = ringbuffer
        self.data_byte_size = ringbuffer.data_byte_size
        self.metadata_byte_size = ringbuffer.metadata_byte_size

    def __call__(self, data, metadata):
        if data.nbytes != self.data_byte_size or metadata.nbytes != self.metadata_byte_size:
            buffer_metadata = self.ringbuffer.get_metadata()
            print(f"""Importer to ringbuffer {buffer_metadata['name']} received data or metadata from {self.ufunc.__name__} with the wrong size.
                    Shutting down the buffer and the importer.""")
            self.ringbuffer.send_flush_event()
            return False
        if data is None:
            self.ringbuffer.send_flush_event()
            return False
        with ringbuffer.Writer(self.ringbuffer) as slot:
            slot[: self.data_byte_size] = data.view(np.uint8)
            slot[self.data_byte_size :] = metadata.view(np.uint8)
        return True


class Exporter:
    def __init__(self, ringbuffer, name):
        self.ringbuffer = ringbuffer
        self.data_byte_size = ringbuffer.data_byte_size
        self.data_dtype = ringbuffer.data_dtype
        self.metadata_dtype = ringbuffer.metadata_dtype

    def __call__(self):
        while True:
            with ringbuffer.Reader(self.ringbuffer) as slot:
                if slot is None:
                    yield None
                    break
                data = slot[: self.data_byte_size].view(self.data_dtype)
                metadata = slot[self.data_byte_size :].view(self.metadata_dtype)
                yield data, metadata


class Processor:
    """
    return of the ufunc(data)
    None -> discard event
    list -> mapping to the output ringbuffers
        None -> dont write to the corresponding output ringbuffer
        numpy strucutred array -> write to the corresponding output ringbuffer
        list of numpy structured arrays -> each array is written into a slot of the corresponding output ringbuffer
    """

    def __init__(self, input_ringbuffer, output_ringbuffers, ufunc, function_name=None, testing=False):
        self.input_ringbuffer = input_ringbuffer
        self.data_byte_size = input_ringbuffer.data_byte_size
        self.output_ringbuffers = output_ringbuffers
        self.number_of_output_buffers = len(output_ringbuffers)
        self.ufunc = ufunc
        self.function_name = function_name
        if self.function_name is None:
            self.function_name = ufunc.__name__

        self.testing = testing  # TODO implement testing for all points of failure

    def shutdown(self):
        self.input_ringbuffer.send_flush_event()
        for output_ringbuffer in self.output_ringbuffers:
            output_ringbuffer.send_flush_event()

    def error(self, message, data):
        metadata = self.input_ringbuffer.get_metadata()
        msg = f"Error in {self.function_name} Proccessing from {metadata['name']}: {message}"
        if self.testing:
            msg += "\n\tShutting down the buffer and its child buffers."
            msg += f"\n\tData: {data}"  # TODO saving to npy file would be better
            self.shutdown()
        print(msg)

    def evaluate(self, data):
        try:
            return_of_ufunc = self.ufunc(data)
        except Exception as e:
            self.error(f"Exception: {e}", data)
            return None
        return return_of_ufunc

    def map_ufunc_to_buffers(self, return_of_ufunc, metadata):
        if not isinstance(return_of_ufunc, list) or len(return_of_ufunc) != self.number_of_output_buffers:
            self.error(
                "Output of the processing function is not a list or has the wrong length.", return_of_ufunc
            )  # TODO this is not the right data
            return

        for data_list, output_ringbuffer in zip(return_of_ufunc, self.output_ringbuffers):
            if data_list is None:
                continue
            if not isinstance(data_list, list):
                data_list = [data_list]
            for data in data_list:
                self.write_data_to_buffer(data, metadata, output_ringbuffer)

    def write_data_to_buffer(self, data, metadata, output_ringbuffer):
        data_byte_size = output_ringbuffer.data_byte_size
        if data is None:
            return
        if not isinstance(data, np.ndarray) or data.dtype != output_ringbuffer.data_dtype:
            self.error(
                "Output of the processing function is not a numpy array or has the wrong dtype.", data
            )  # TODO this is not the right data
            return
        if data.nbytes != output_ringbuffer.data_byte_size:
            self.error("Output of the processing function has the wrong size.", data)
            return
        with ringbuffer.Writer(output_ringbuffer) as output_slot:
            output_slot[:data_byte_size] = data.view(np.uint8)
            output_slot[data_byte_size:] = metadata.view(np.uint8)

    def __call__(self):
        while True:
            with ringbuffer.Reader(self.input_ringbuffer) as input_slot:
                if input_slot is None:
                    self.shutdown()
                    break
                data = input_slot[: self.data_byte_size].view(self.input_ringbuffer.data_dtype)
                metadata = input_slot[self.data_byte_size :].view(self.input_ringbuffer.metadata_dtype)

                ret = self.evaluate(data)
                if ret is None:
                    continue
                self.map_ufunc_to_buffers(ret, metadata)


if __name__ == "__main__":
    EVENT_COUNT = 10

    OSCILLOSCOPE_LENGTH = 1000
    PULSE_SIGMA = 10
    MAX_PULSE_HEIGHT = 100

    def pulse():
        x = np.arange(OSCILLOSCOPE_LENGTH)
        # random position and height of the pulse
        pulse_position = np.random.randint(0, OSCILLOSCOPE_LENGTH)
        pulse_height = np.random.randint(0, MAX_PULSE_HEIGHT)
        return np.exp(-((x - pulse_position) ** 2) / (2 * PULSE_SIGMA**2)) * pulse_height

    OSC_DTYPE = np.dtype([("osc", np.float64)])

    def oscilloscope():
        for i in range(EVENT_COUNT):
            data = np.zeros(OSCILLOSCOPE_LENGTH, dtype=OSC_DTYPE)
            data["osc"] = pulse()
            metadata = np.zeros(1, dtype=DAQRingBuffer.metadata_dtype)
            metadata["counter"] = i
            metadata["timestamp"] = 0
            metadata["deadtime"] = 0
            yield data, metadata
        yield None

    PULSE_HEIGHT_DTYPE = np.dtype([("pulse_height", np.float64)])

    def pulse_height_analyzer(data):
        pulse_height = np.max(data["osc"])
        return [np.array([pulse_height], dtype=PULSE_HEIGHT_DTYPE)]

    def printer(exporter):
        generator = exporter()
        while True:
            ret = next(generator)
            if ret is None:
                break
            print(ret)

    osc_buffer = DAQRingBuffer("oscilloscope", 10, OSCILLOSCOPE_LENGTH, OSC_DTYPE)
    pulse_height_buffer = DAQRingBuffer("pulse_height", 10, 1, PULSE_HEIGHT_DTYPE)

    osc_importer = Importer(osc_buffer, oscilloscope)
    pulse_height_processor = Processor(osc_buffer, [pulse_height_buffer], pulse_height_analyzer)
    pulse_height_exporter = Exporter(pulse_height_buffer, "Export")

    from multiprocessing import Process

    imp = Process(target=osc_importer)
    ana = Process(target=pulse_height_processor)
    exp = Process(target=printer, args=(pulse_height_exporter,))

    exp.start()
    ana.start()
    imp.start()

    imp.join()
    ana.join()
    exp.join()
