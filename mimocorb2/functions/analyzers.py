from mimocorb2.worker_templates import Processor
from mimocorb2.mimo_worker import BufferIO
import scipy.signal as signal


def pha(buffer_io: BufferIO):
    """Analyze an oscilloscope like buffer using scipy.signal.find_peaks.
    Only one channel can be analyzed at a time.

    Parameters are used from the configuration file.
    """
    processor = Processor(buffer_io)
    if len(processor.writers) != 1:
        raise ValueError("mimocorb2.analyzers.pha only supports one sink.")

    config = processor.config
    channel = config.get('channel')
    height = config.get('height', None)
    threshold = config.get('threshold', None)
    distance = config.get('distance', None)
    prominence = config.get('prominence', None)
    width = config.get('width', None)
    wlen = config.get('wlen', None)
    rel_height = config.get('rel_height', 0.5)
    plateau_size = config.get('plateau_size', None)

    example_data_in = processor.data_example
    channels = example_data_in.dtype.names
    if channel not in channels:
        raise ValueError(f"Channel {channel} is not available in the source.")

    data_example_out = processor.io.write[0].data_example.copy()
    requested_parameters = data_example_out.dtype.names
    if data_example_out.size != 1:
        raise ValueError("mimocorb2.analyzers.pha only data_length = 1 in the sink.")

    for parameter in requested_parameters:
        if parameter in ['position']:
            pass
        elif parameter in ['peak_heights']:
            if height is None:
                raise ValueError(f"Parameter {parameter} is only possible with height config")
        elif parameter in ['left_thresholds', 'right_thresholds']:
            if threshold is None:
                raise ValueError(f"Parameter {parameter} is only possible with threshold config")
        elif parameter in ['prominences', 'left_bases', 'right_bases']:
            if prominence is None:
                raise ValueError(f"Parameter {parameter} is only possible with prominence config")
        elif parameter in ['widths', 'width_heights', 'left_ips', 'right_ips']:
            if width is None:
                raise ValueError(f"Parameter {parameter} is only possible with width config")
        elif parameter in ['plateau_sizes', 'left_edges', 'right_edges']:
            if plateau_size is None:
                raise ValueError(f"Parameter {parameter} is only possible with plateau_size config")
        else:
            raise ValueError(f"Parameter {parameter} is not supported")

    def ufunc(data):
        peaks, properties = signal.find_peaks(
            x=data[channel],
            height=height,
            threshold=threshold,
            distance=distance,
            prominence=prominence,
            width=width,
            wlen=wlen,
            rel_height=rel_height,
            plateau_size=plateau_size,
        )
        for i in range(len(peaks)):
            for parameter in requested_parameters:
                if parameter in ['position']:
                    data_example_out['position'] = peaks[i]
                else:
                    data_example_out[parameter] = properties[parameter][i]
            return [data_example_out]

    processor(ufunc)
