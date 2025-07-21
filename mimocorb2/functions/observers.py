from mimocorb2.worker_templates import Observer
import matplotlib.pyplot as plt
import numpy as np
import time


def oscilloscope(buffer_io):
    """mimoCoRB2 Function: Show an Osilloscope plot of the buffer.

    Observes data from a buffer and shows it as an oscilloscope plot.

    Type
    ----
    Observer

    Buffers
    -------
    sources
        0
    sinks
        0
    observes
        1

    Configs
    -------
    ylim : tuple of float, optional (default=None)
        (min, max) of the y-axis. If None, the y-axis will be autoscaled upon each update.
    t_scaling : tuple of float, optional (default=(1, 0, 'Samples'))
        (scaling, offset, unit) for the x-axis. The x-axis will be scaled accordingly.
    y_scaling : tuple of float, optional (default=(1, 0, 'Value'))
        (scaling, offset, unit) for the y-axis. The y-axis will be scaled accordingly.
    channels : list of str, optional (default=None)
        List of channel names to be plotted. If None, all available channels will be plotted.
    trigger_level : float, optional (default=None)
        If specified, a horizontal line will be drawn at this level to indicate the trigger level.
    update_interval : float, optional (default=1)
        Interval to update the plot in seconds. Default is 1 second.
    """
    # Get info from the buffer
    observer = Observer(buffer_io)
    number_of_samples = observer.data_example.size
    available_channels = observer.data_example.dtype.names

    # Get the configuration parameters
    update_interval = observer.config.get('update_interval', 1)
    ylim = observer.config.get('ylim')
    t_scaling = observer.config.get('t_scaling', (1, 0, 'Samples'))  # (scaling, offset, unit)
    y_scaling = observer.config.get('y_scaling', (1, 0, 'Value'))  # (scaling, offset, unit)
    requested_channels = observer.config.get('channels', available_channels)
    trigger_level = observer.config.get('trigger_level')

    # Apply the t scaling
    t = np.arange(number_of_samples) * t_scaling[0] + t_scaling[1]

    # Get the channels to be plotted
    for rch in requested_channels:
        if rch not in available_channels:
            raise ValueError(f"Channel '{rch}' not found in the data")
    channels = requested_channels

    fig = plt.figure()
    fig.canvas.manager.set_window_title(f'Oscilloscope: {observer.name}')
    ax = fig.add_subplot(111)

    # set limits
    ax.set_xlim(t[0], t[-1])
    if ylim is not None:
        ax.set_ylim(ylim[0], ylim[1])

    if trigger_level is not None:
        ax.hlines(trigger_level, t[0], t[-1], linestyles='dotted', label='Trigger Level')

    ys = {ch: np.zeros(number_of_samples) for ch in channels}
    alpha = 0.5 if len(channels) > 1 else 1.0
    lines = {ch: ax.plot(t, ys[ch], alpha=alpha, label=ch)[0] for ch in channels}

    ax.set_xlabel(t_scaling[2])
    ax.set_ylabel(y_scaling[2])

    # create the legend and make it interactive
    legend = ax.legend(title='Click to hide/show')
    legend_texts = legend.get_texts()
    legend_lines = legend.get_lines()
    legend_artists = legend_texts + legend_lines

    for a in legend_artists:
        a.set_picker(5)

    artist_to_channel = {artist: ch for artist, ch in zip(legend_artists, 2 * channels)}
    channel_to_texts = {artist_to_channel[text]: text for text in legend_texts}
    channel_to_lines = {artist_to_channel[patch]: patch for patch in legend_lines}

    def on_pick(event):
        artist = event.artist
        if artist not in legend_artists:
            return
        ch = artist_to_channel[artist]
        # Toggle visibility of plot
        visible = not lines[ch].get_visible()
        lines[ch].set_visible(visible)
        # Toggle visibility of legend
        channel_to_texts[ch].set_alpha(1.0 if visible else 0.2)
        channel_to_lines[ch].set_alpha(1.0 if visible else 0.2)
        # Update the plot
        fig.canvas.draw()

    fig.canvas.mpl_connect('pick_event', on_pick)

    plt.ion()
    plt.show()

    last_update = time.time()

    generator = observer()
    while True:
        if time.time() - last_update > update_interval:
            data, metadata = next(generator)
            if data is None:
                break
            for ch in channels:
                ys[ch] = data[ch]
                lines[ch].set_ydata(ys[ch])
            if ylim is None:
                ax.relim()
                ax.autoscale_view()
            fig.canvas.draw()
            last_update = time.time()
        fig.canvas.flush_events()
        time.sleep(0.05)
