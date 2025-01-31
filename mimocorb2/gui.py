from PyQt5 import QtWidgets, uic, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
import time
import os


WIDTH = 5
HEIGHT = 4
DPI = 100

NUMBER_OF_DATA_POINTS = 10

class BufferManagerApp(QtWidgets.QMainWindow):
    def __init__(self, control):
        self.COLORS = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        super().__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), "gui.ui"), self)

        self.control = control

        buffers = control.setup['Buffers'].keys()
        workers = control.setup['Workers'].keys()

        # Setup matplotlib canvases
        self.rate_canvas = RateCanvas(self.rate_tab, buffers, workers, title="Rate Information")
        self.process_canvas = WorkerCanvas(self.process_tab, buffers, workers, title="Process Information")
        self.buffer_canvas = BufferCanvas(self.buffer_tab, buffers, workers, title="Buffer Information")

        # Add timers for real-time updates
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(2000)  # Update every second

        # Connect control buttons
        self.shutdownRootBuffer.clicked.connect(self.action_shutdownRootBuffer)
        self.shutdownAllBuffers.clicked.connect(self.action_shutdownAllBuffers)
        self.killWorkers.clicked.connect(self.action_killWorkers)
        self.exitButton.clicked.connect(self.action_exit)

    def update_plots(self):
        buffer_stats = self.control.get_buffer_stats()
        worker_stats = self.control.get_active_workers()

        self.rate_canvas.update_plot(buffer_stats, worker_stats)
        self.process_canvas.update_plot(buffer_stats, worker_stats)
        self.buffer_canvas.update_plot(buffer_stats, worker_stats)

    def closeEvent(self, event):
        """Handle the window close event."""
        # Replace this with your test condition
        if sum(self.control.get_active_workers().values()) != 0:
            # Show a warning message
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Warning",
                "Some processes are incomplete. Are you sure you want to exit?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.No:
                event.ignore()
                return
        # Proceed with closing
        event.accept()

    def action_shutdownRootBuffer(self):
        self.control.clean_shutdown()

    def action_shutdownAllBuffers(self):
        self.control.hard_shutdown()

    def action_killWorkers(self):
        self.control.kill_workers()

    def action_exit(self):
        self.close()


class PlotCanvas(FigureCanvas):
    def __init__(self, parent, buffers, workers, width=WIDTH, height=HEIGHT, dpi=100, title=""):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        self.setParent(parent)
        self.axes.set_title(title)

        self.buffers = buffers
        self.workers = workers

        self.init_plot()
        fig.tight_layout()


class BufferCanvas(PlotCanvas):
    def init_plot(self):
        colors = ["#E24A33", "#FBC15E", "#2CA02C", "#FFFFFF"]
        #colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        # the ordering of the bars is important
        self.bar_filled = self.axes.bar(self.buffers, 0, label="Filled", color=colors[0])
        self.bar_working = self.axes.bar(self.buffers, 0, label="Working", color=colors[1])
        self.bar_empty = self.axes.bar(self.buffers, 1, label="Empty", color=colors[2])
        self.shutdown_overlay = self.axes.bar(self.buffers, 0, label="Shutdown", color=colors[3], alpha=0.3, hatch="//")

        self.axes.set_ylim(0, 1)
        self.axes.legend(loc="upper right")
        self.axes.tick_params(axis="x", rotation=45)
        self.axes.set_ylabel("Ratio")

    def update_plot(self, buffer_stats, worker_stats):
        filled = np.array([buffer_stats[key]["filled_slots"] for key in self.buffers])
        empty = np.array([buffer_stats[key]["empty_slots"] for key in self.buffers])
        shutdown = np.array([buffer_stats[key]["flush_event_received"] for key in self.buffers])

        for bar, new_height in zip(self.bar_filled, [1] * len(self.buffers)):
            bar.set_height(new_height)
        for bar, new_height in zip(self.bar_working, 1 - filled):
            bar.set_height(new_height)
        for bar, new_height in zip(self.bar_empty, empty):
            bar.set_height(new_height)
        for bar, is_shutdown in zip(self.shutdown_overlay, shutdown):
            bar.set_height(1 if is_shutdown else 0)

        self.draw()


class WorkerCanvas(PlotCanvas):
    def init_plot(self):
        colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        self.bars = self.axes.bar(self.workers, 0, label="Workers", color = colors[0])

        self.resize_axis(1)
        self.axes.tick_params(axis="x", rotation=45)
        for label in self.axes.get_xticklabels():
            label.set_horizontalalignment('right')
        self.axes.set_ylabel("Number of Workers")

    def update_plot(self, buffer_stats, worker_stats):
        for bar, key in zip(self.bars, self.workers):
            n = worker_stats[key]
            if n > self.max:
                self.resize_axis(n)
            bar.set_height(n)

        self.draw()

    def resize_axis(self, n):
        self.max = n
        self.axes.set_ylim(0, 1.1 * self.max)
        self.axes.set_yticks(np.arange(self.max + 1))


class RateCanvas(PlotCanvas):
    def init_plot(self):
        self.rates = {key: [0] * NUMBER_OF_DATA_POINTS for key in self.buffers}
        self.last_event_count = {key: 0 for key in self.buffers}
        self.last_update_time = {key: time.time() for key in self.buffers}
        self.lines = {}
        for key in self.buffers:
            self.lines[key] = self.axes.plot()
        self.lines = {
            key: self.axes.plot(np.arange(-NUMBER_OF_DATA_POINTS, 0) + 1, self.rates[key], label=key)[0]
            for key in self.buffers
        }

        self.axes.legend(loc="upper left")
        self.axes.set_ylim(0.1, 2000)
        self.axes.set_yscale("log")
        self.axes.set_ylabel("Rate (events/s)")
        for label in self.axes.get_xticklabels():
            label.set_horizontalalignment('right')

    def update_plot(self, buffer_stats, worker_stats):
        for key in self.buffers:
            event_count = buffer_stats[key]["event_count"]
            update_time = time.time()

            rate = (event_count - self.last_event_count[key]) / (update_time - self.last_update_time[key])
            self.rates[key].append(rate)
            self.rates[key].pop(0)

            self.last_event_count[key] = event_count
            self.last_update_time[key] = update_time

            self.lines[key].set_ydata(self.rates[key])

        # self.axes.relim()
        # self.axes.autoscale_view()
        # self.axes.set_ylim(bottom=0)
        self.draw()
