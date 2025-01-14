from mimocorb2.function_templates import Observer
import matplotlib.pyplot as plt
import numpy as np
import time

def oscilloscope(*mimo_args):
    # TODO axis labeling and range should be better
    observer = Observer(mimo_args)
    data_example = observer.observer.buffer_info['data_example']
    tmax = data_example.size
    channels = data_example.dtype.names

    update_interval = observer.config.get('update_interval', 1)
    ylim = observer.config.get('ylim', (-750,0))

    fig = plt.figure()
    fig.canvas.manager.set_window_title('Oscilloscope')
    ax = fig.add_subplot(111)
    ax.set_xlim(0, tmax)
    ax.set_ylim(ylim[0], ylim[1])

    ax.hlines(0, 0, tmax, linestyles='dashed')

    ys = {ch: np.zeros(tmax) for ch in channels}
    lines = {ch: ax.plot(ys[ch], label=ch)[0] for ch in channels}
    
    ax.set_xlabel('Time [Samples]')
    ax.set_ylabel('Amplitude [ADC]')

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
            fig.canvas.draw()
            last_update = time.time()
        fig.canvas.flush_events()
        time.sleep(0.05)
