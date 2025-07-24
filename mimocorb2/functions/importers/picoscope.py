"""
**picoscope_source**: Read waveform data from usb oscilloscpe
"""

import numpy as np
from mimocorb2 import Importer
from threading import Event
import time
import ctypes
from picosdk.ps3000a import ps3000a as ps
from picosdk.functions import mV2adc, assert_pico_ok
from picosdk.errors import PicoSDKCtypesError


class pico3000:
    """
    Access PS3000A scope in rapid block mode.
    Code derived from picoScope python SDK 3000A rapid block mode example code
    """

    def __init__(self, data_example: np.ndarray, config_dict=None):
        """evalutate configuation dictionary and set up callback and variables"""
        # Create a threading Event to speed up data copy (no polling required)
        self.callback_event = Event()
        self.callback_event.clear()

        # Initialize picoScope and all needed variables
        self.trigger_counter = 0
        self.chandle = ctypes.c_int16()
        self.status = {"openunit": ps.ps3000aOpenUnit(ctypes.byref(self.chandle), None)}
        try:
            assert_pico_ok(self.status["openunit"])
        except PicoSDKCtypesError:
            # status number of openunit
            powerstate = self.status["openunit"]

            if powerstate == 282:
                # Changes the power input to "PICO_POWER_SUPPLY_NOT_CONNECTED"
                self.status["ChangePowerSource"] = ps.ps3000aChangePowerSource(self.chandle, 282)
            elif powerstate == 286:
                # Changes the power input to "PICO_USB3_0_DEVICE_NON_USB3_0_PORT"
                self.status["ChangePowerSource"] = ps.ps3000aChangePowerSource(self.chandle, 286)
            else:
                raise
            assert_pico_ok(self.status["ChangePowerSource"])

        self.max_adc = ctypes.c_int16(0)
        self.status["maximumValue"] = ps.ps3000aMaximumValue(self.chandle, ctypes.byref(self.max_adc))
        assert_pico_ok(self.status["maximumValue"])
        self.max_adc_value = self.max_adc.value

        # Configuration (for Picoscope 3000A)
        self.capture_channelA = ps.PS3000A_CHANNEL["PS3000A_CHANNEL_A"]
        self.capture_channelB = ps.PS3000A_CHANNEL["PS3000A_CHANNEL_B"]
        self.capture_channelC = ps.PS3000A_CHANNEL["PS3000A_CHANNEL_C"]
        self.capture_channelD = ps.PS3000A_CHANNEL["PS3000A_CHANNEL_D"]
        self.channel_coupling = ps.PS3000A_COUPLING["PS3000A_" + config_dict["channel_coupling"]]

        if "channel_range" in config_dict:
            channel_range = ps.PS3000A_RANGE["PS3000A_" + config_dict["channel_range"]]
            self.channelA_range = channel_range
            self.channelB_range = channel_range
            self.channelC_range = channel_range
            self.channelD_range = channel_range
        else:
            channel_range = ps.PS3000A_RANGE["PS3000A_20V"]
            self.channelA_range = channel_range
            self.channelB_range = channel_range
            self.channelC_range = channel_range
            self.channelD_range = channel_range
            if "channelA_range" in config_dict:
                self.channelA_range = ps.PS3000A_RANGE["PS3000A_" + config_dict["channelA_range"]]
            if "channelB_range" in config_dict:
                self.channelB_range = ps.PS3000A_RANGE["PS3000A_" + config_dict["channelB_range"]]
            if "channelC_range" in config_dict:
                self.channelC_range = ps.PS3000A_RANGE["PS3000A_" + config_dict["channelC_range"]]
            if "channelD_range" in config_dict:
                self.channelD_range = ps.PS3000A_RANGE["PS3000A_" + config_dict["channelD_range"]]

        channelInputRanges = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000]
        self.chA_range_value = channelInputRanges[self.channelA_range]
        self.chB_range_value = channelInputRanges[self.channelB_range]
        self.chC_range_value = channelInputRanges[self.channelC_range]
        self.chD_range_value = channelInputRanges[self.channelD_range]

        if "analogue_offset" in config_dict:
            analogue_offset = config_dict["analogue_offset"]  # in V and not adc!
            self.analogue_offset_chA = analogue_offset
            self.analogue_offset_chB = analogue_offset
            self.analogue_offset_chC = analogue_offset
            self.analogue_offset_chD = analogue_offset
        else:
            self.analogue_offset_chA = 0
            self.analogue_offset_chB = 0
            self.analogue_offset_chC = 0
            self.analogue_offset_chD = 0
            if "analogue_offset_chA" in config_dict:
                self.analogue_offset_chA = config_dict["analogue_offset_chA"]
            if "analogue_offset_chB" in config_dict:
                self.analogue_offset_chB = config_dict["analogue_offset_chB"]
            if "analogue_offset_chC" in config_dict:
                self.analogue_offset_chC = config_dict["analogue_offset_chC"]
            if "analogue_offset_chD" in config_dict:
                self.analogue_offset_chD = config_dict["analogue_offset_chD"]

        self.number_of_channels = len(data_example.dtype.names)  # number of channels to capture

        self.trigger_channel = config_dict["trigger_channel"]
        threshold = config_dict["trigger_level"]
        if self.trigger_channel == "EXT":
            # external trigger
            # range for External Trigger is 5000 mV
            print(self.max_adc)

            self.trigger_level = round((threshold * self.max_adc.value) / 5000.0)
            trigger_channel_name = "PS3000A_EXTERNAL"
        else:
            # trigger channels A - D
            if self.trigger_channel not in ["A", "B", "C", "D"][: self.number_of_channels]:
                self.trigger_channel = "A"
            trigger_channel_name = "PS3000A_CHANNEL_" + self.trigger_channel
            if self.trigger_channel == "A":
                self.trigger_level = mV2adc(threshold, self.channelA_range, self.max_adc)
            elif self.trigger_channel == "B":
                self.trigger_level = mV2adc(threshold, self.channelB_range, self.max_adc)
            elif self.trigger_channel == "C":
                self.trigger_level = mV2adc(threshold, self.channelC_range, self.max_adc)
            elif self.trigger_channel == "D":
                self.trigger_level = mV2adc(threshold, self.channelD_range, self.max_adc)

        self.trigger_channel = ps.PS3000A_CHANNEL[trigger_channel_name]

        if "trigger_direction" in config_dict:
            self.trigger_direction = ps.PS3000A_THRESHOLD_DIRECTION["PS3000A_" + config_dict["trigger_direction"]]
        else:
            self.trigger_direction = ps.PS3000A_THRESHOLD_DIRECTION["PS3000A_RISING"]

        self.trigger_delay = 0  # measured in sample cycles!
        self.auto_trigger = 2**16  # in ms
        self.pre_trigger_samples = config_dict["pre_trigger_samples"]
        self.total_samples = len(data_example)  # total samples to capture
        self.post_trigger_samples = self.total_samples - self.pre_trigger_samples

        self.timebase = config_dict[
            "timebase"
        ]  # the magic numbers go 'wheee'. Apparently it's the fastest the 3404D will go
        self.time_interval_ns = ctypes.c_float()
        # if int(self.time_interval_ns) != config_dict["time_interval_ns"]:
        #    raise ValueError("ERROR!! Sample time requested by timebase and resulting time_interval_ns do not match!")

        self.number_of_memory_segments = config_dict["number_of_memory_segments"]

        self.returned_max_samples = ctypes.c_int32()
        self.oversample = ctypes.c_int16()  # why do we even bother, it's not used according to the SDK anyways
        self.segment_index = 0

        #!if self.sink.values_per_slot < self.total_samples:
        #!    raise ValueError("ERROR! Ringbuffer size ({:d}) smaller than total samples to capture ({:d})!".format(
        #!        self.sink.values_per_slot, self.total_samples))

        # Initialize picoscope (see example)
        self.status["setChA"] = ps.ps3000aSetChannel(
            self.chandle,
            self.capture_channelA,
            1,  # enabled
            self.channel_coupling,
            self.channelA_range,
            self.analogue_offset_chA,
        )
        assert_pico_ok(self.status["setChA"])
        if self.number_of_channels > 1:
            self.status["setChB"] = ps.ps3000aSetChannel(
                self.chandle,
                self.capture_channelB,
                1,  # enabled
                self.channel_coupling,
                self.channelB_range,
                self.analogue_offset_chB,
            )
            assert_pico_ok(self.status["setChB"])
        if self.number_of_channels > 2:
            self.status["setChC"] = ps.ps3000aSetChannel(
                self.chandle,
                self.capture_channelC,
                1,  # enabled
                self.channel_coupling,
                self.channelC_range,
                self.analogue_offset_chC,
            )
            assert_pico_ok(self.status["setChC"])
        if self.number_of_channels > 3:
            self.status["setChD"] = ps.ps3000aSetChannel(
                self.chandle,
                self.capture_channelD,
                1,  # enabled
                self.channel_coupling,
                self.channelD_range,
                self.analogue_offset_chD,
            )
            assert_pico_ok(self.status["setChD"])
        self.status["trigger"] = ps.ps3000aSetSimpleTrigger(
            self.chandle,
            1,  # enabled
            self.trigger_channel,
            self.trigger_level,
            self.trigger_direction,
            self.trigger_delay,
            self.auto_trigger,
        )
        assert_pico_ok(self.status["trigger"])
        self.status["getTimebase2"] = ps.ps3000aGetTimebase2(
            self.chandle,
            self.timebase,
            self.total_samples,
            ctypes.byref(self.time_interval_ns),
            self.oversample,
            ctypes.byref(self.returned_max_samples),
            self.segment_index,
        )
        assert_pico_ok(self.status["getTimebase2"])

        # Setup memory segments in picoScope
        if (self.number_of_channels * self.total_samples * self.number_of_memory_segments) > 128e6:
            raise ValueError(
                "Number of memory segments too high! PicoScope 3404D only supports up to 128MS. This configuration requires {:d} samples".format(
                    self.number_of_channels * self.total_samples * self.number_of_memory_segments
                )
            )

        ctotal_samples = ctypes.c_int32(self.total_samples)
        self.status["MemorySegments"] = ps.ps3000aMemorySegments(
            self.chandle, self.number_of_memory_segments, ctypes.byref(ctotal_samples)
        )
        assert_pico_ok(self.status["MemorySegments"])

        self.status["SetNoOfCaptures"] = ps.ps3000aSetNoOfCaptures(self.chandle, self.number_of_memory_segments)
        assert_pico_ok(self.status["SetNoOfCaptures"])

        # Initialize raw memory segments pass to the picoScope
        self.chA_buffers = []
        self.chB_buffers = []
        self.chC_buffers = []
        self.chD_buffers = []
        for i in range(self.number_of_memory_segments):
            buffer = np.empty(self.total_samples, dtype=np.dtype('int16'))
            self.status["setDataBuffersA"] = ps.ps3000aSetDataBuffer(
                self.chandle,
                self.capture_channelA,
                buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                self.total_samples,
                i,  # segment index
                ps.PS3000A_RATIO_MODE["PS3000A_RATIO_MODE_NONE"],
            )
            self.chA_buffers.append(buffer)
            assert_pico_ok(self.status["setDataBuffersA"])

        if self.number_of_channels > 1:
            for i in range(self.number_of_memory_segments):
                buffer = np.empty(self.total_samples, dtype=np.dtype('int16'))
                self.status["setDataBuffersB"] = ps.ps3000aSetDataBuffer(
                    self.chandle,
                    self.capture_channelB,
                    buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                    self.total_samples,
                    i,  # segment index
                    ps.PS3000A_RATIO_MODE["PS3000A_RATIO_MODE_NONE"],
                )
                self.chB_buffers.append(buffer)
                assert_pico_ok(self.status["setDataBuffersB"])

        if self.number_of_channels > 2:
            for i in range(self.number_of_memory_segments):
                buffer = np.empty(self.total_samples, dtype=np.dtype('int16'))
                self.status["setDataBuffersC"] = ps.ps3000aSetDataBuffer(
                    self.chandle,
                    self.capture_channelC,
                    buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                    self.total_samples,
                    i,  # segment index
                    ps.PS3000A_RATIO_MODE["PS3000A_RATIO_MODE_NONE"],
                )
                self.chC_buffers.append(buffer)
                assert_pico_ok(self.status["setDataBuffersC"])
        if self.number_of_channels > 3:
            for i in range(self.number_of_memory_segments):
                buffer = np.empty(self.total_samples, dtype=np.dtype('int16'))
                self.status["setDataBuffersD"] = ps.ps3000aSetDataBuffer(
                    self.chandle,
                    self.capture_channelD,
                    buffer.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),
                    self.total_samples,
                    i,  # segment index
                    ps.PS3000A_RATIO_MODE["PS3000A_RATIO_MODE_NONE"],
                )
                self.chD_buffers.append(buffer)
                assert_pico_ok(self.status["setDataBuffersD"])

    def __del__(self):
        # Stop the scope
        self.callback_event.clear()
        self.status["stop"] = ps.ps3000aStop(self.chandle)
        assert_pico_ok(self.status["stop"])
        self.status["close"] = ps.ps3000aCloseUnit(self.chandle)
        assert_pico_ok(self.status["close"])

    def get_data_callback(self, par=None):
        global callback_time
        callback_time = time.time_ns()
        self.callback_event.set()

    def __call__(self):
        """provide data to caller via yield()"""
        global callback_time
        # overflow = np.zeros(self.number_of_memory_segments, dtype=np.int16)
        # overflow_ptr = overflow.ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
        overflow = (ctypes.c_int16 * self.number_of_memory_segments)()
        overflow_ptr = ctypes.byref(overflow)
        cint32_total_samples = ctypes.c_int32(self.total_samples)
        time_indisposed_ms = ctypes.c_int32(
            0
        )  # looks nice, but upon testing this showed to be useless (always returning "2")
        CALLBACK_FUNC = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)
        data_callback = CALLBACK_FUNC(self.get_data_callback)
        callback_time = 0
        self.status["runBlock"] = ps.ps3000aRunBlock(
            self.chandle,
            self.pre_trigger_samples,
            self.post_trigger_samples,
            self.timebase,
            self.oversample,
            ctypes.byref(
                time_indisposed_ms
            ),  # time indisposed ms (the time the picoscope spent actually capturing data)
            0,  # segment index
            data_callback,  # callback function
            None,
        )  # pParameter
        assert_pico_ok(self.status["runBlock"])
        # start_time = time.time_ns()
        # ready = ctypes.c_int16(0)
        # check = ctypes.c_int16(0)

        # initialize array for data to pass to rbInput
        data = np.empty((self.number_of_channels, self.total_samples), dtype=np.float32)

        while True:
            # Event from callback function (this blocks until callback_event is set get_data_callback() )
            self.callback_event.wait()

            self.status["getValuesBulk"] = ps.ps3000aGetValuesBulk(
                self.chandle,
                ctypes.byref(cint32_total_samples),
                0,  # start segment
                self.number_of_memory_segments - 1,  # last segment
                0,  # downsample ratio
                ps.PS3000A_RATIO_MODE["PS3000A_RATIO_MODE_NONE"],
                overflow_ptr,
            )
            assert_pico_ok(self.status["getValuesBulk"])
            # Testing found that this is returning nonsensical data -> probably not implemented (correctly) in the picoscope driver.
            # So as of now this is not used for the time offset calculation
            time_offsets = np.empty(
                self.number_of_memory_segments, dtype=np.dtype('int64')
            )  # or int16?!? See example code
            time_units = np.empty(self.number_of_memory_segments, dtype=np.dtype('int32'))  # this is even stranger
            self.status["TriggerTimeOffset"] = ps.ps3000aGetValuesTriggerTimeOffsetBulk64(
                self.chandle,
                time_offsets.ctypes.data_as(ctypes.POINTER(ctypes.c_int64)),
                time_units.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
                0,
                self.number_of_memory_segments - 1,
            )
            assert_pico_ok(self.status["TriggerTimeOffset"])
            # Starting the new rapid block capture now, to waste less time
            self.callback_event.clear()
            self.status["runBlock"] = ps.ps3000aRunBlock(
                self.chandle,
                self.pre_trigger_samples,
                self.post_trigger_samples,
                self.timebase,
                self.oversample,
                ctypes.byref(time_indisposed_ms),  # time indisposed ms
                0,  # segment index
                data_callback,  # callback function
                None,
            )  # pParameter
            assert_pico_ok(self.status["runBlock"])
            # stop_time = time.time_ns()
            # processing_time = (stop_time - start_time) // 1e6  # Transform ns to ms
            # capture_time = (callback_time - start_time) // 1e6  # Transform ns to ms
            # deadtime = 1 - capture_time / processing_time  # in percent
            # start_time = stop_time
            # ready = ctypes.c_int16(0)
            # check = ctypes.c_int16(0)
            # Bulk convert all channels from ADC to mV using numpy vectorization. Using a big numpy array instead of
            # a list of arrays would be better (performance wise), but memory segmentation and views are a b*** to debug
            # and virtually impossible to consistently (aka cross platform/cross version) pass correctly to the C-style function API
            chA_buffers_mV = np.stack(self.chA_buffers, axis=0) * (self.chA_range_value / self.max_adc_value)
            if self.number_of_channels > 1:
                chB_buffers_mV = np.stack(self.chB_buffers, axis=0) * (self.chB_range_value / self.max_adc_value)
            if self.number_of_channels > 2:
                chC_buffers_mV = np.stack(self.chC_buffers, axis=0) * (self.chC_range_value / self.max_adc_value)
            if self.number_of_channels > 3:
                chD_buffers_mV = np.stack(self.chD_buffers, axis=0) * (self.chD_range_value / self.max_adc_value)

            # Put each of the bulk measurements into its own ring buffer slot
            # time_per_sample = processing_time / self.number_of_memory_segments * 1e-3  # in seconds

            for i in range(self.number_of_memory_segments):
                data[0, :] = chA_buffers_mV[i, :]
                if self.number_of_channels > 1:
                    data[1, :] = chB_buffers_mV[i, :]
                if self.number_of_channels > 2:
                    data[2, :] = chC_buffers_mV[i, :]
                if self.number_of_channels > 3:
                    data[3, :] = chD_buffers_mV[i, :]
                # calculate and set metadata
                self.trigger_counter += 1
                # timestamp = stop_time * 1e-9 - processing_time * 1e-3 + i * time_per_sample
                # mdata = (self.trigger_counter, timestamp, deadtime)
                # deliver data (2D numpy) and meta-data (tuple)
                # TODO readd mdata if whished
                yield data


def source(buffer_io):
    """mimoCoRB2 Function: Picoscope Source

    Read waveform data from usb oscilloscpe

    Type
    ----
    Importer

    Buffers
    -------
    sources
        0
    sinks
        1
    observes
        0

    Configs
    -------
    channel_coupling : str
        TODO
    trigger_channel : str
        TODO
    trigger_level : float
        TODO (in mV)
    pre_trigger_samples : int
        TODO
    timebase : int
        TODO (magic number, see picoscope SDK example code)
    number_of_memory_segments : int
        TODO (number of segments to capture, must be <= 128MS)
    channel_range : str, optional (default="20V")
        TODO
    channelA_range : str, optional (only used if channel_range not provided) (default="20V")
    channelB_range : str, optional (only used if channel_range not provided) (default="20V")
    channelC_range : str, optional (only used if channel_range not provided) (default="20V")
    channelD_range : str, optional (only used if channel_range not provided) (default="20V")
    analogue_offset : float, optional (default=0.0)
        TODO (In V and not adc!)
    analogue_offset_chA : float, optional (only used if analogue_offset not provided) (default=0.0)
    analogue_offset_chB : float, optional (only used if analogue_offset not provided) (default=0.0)
    analogue_offset_chC : float, optional (only used if analogue_offset not provided) (default=0.0)
    analogue_offset_chD : float, optional (only used if analogue_offset not provided) (default=0.0)
    trigger_direction : str, optional (default="RISING")
        TODO
    """
    # initialize oszilloscope

    # initalize buffer import; data from __call__-method of class pico3000
    importer = Importer(buffer_io)
    osci = pico3000(importer.data_example, buffer_io.config_dict)
    importer(osci)
    del osci
