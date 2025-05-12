from PyQt5 import QtWidgets, uic, QtCore
from mimocorb2.control import Control
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import numpy as np
import time
import os
import logging
import queue


WIDTH = 5
HEIGHT = 4
DPI = 100

MIN_RATE = 0.1

def get_infos_from_control(control: Control):
    """
    Get the information from the control object.
    """
    buffers = {
        name: {
            'slot_count': buffer.slot_count
        }
        for name, buffer in control.buffers.items()
    }
    workers = {
        name: {'number_of_processes': worker.number_of_processes}
        for name, worker in control.workers.items()
    }
    roots = list(control.roots.keys())
    return {'buffers': buffers, 'workers': workers, 'roots': roots}


class BufferManagerApp(QtWidgets.QMainWindow):
    def __init__(self, command_queue: queue, stats_queue: queue, infos: dict):
        super().__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), "gui.ui"), self)
        
        
        self.COLORS = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        
        self.command_queue = command_queue
        self.stats_queue = stats_queue
        self.infos = infos
        
        
        # Setup matplotlib canvases
        self.rate_canvas = RateCanvas(self.rate_tab, infos, title="Rate Information")
        self.process_canvas = WorkerCanvas(self.process_tab, infos, title="Process Information")
        self.buffer_canvas = BufferCanvas(self.buffer_tab, infos, title="Buffer Information")
        
        # Add timers for real-time updates
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(1000)  # Update every second
        
        # Connect control buttons
        self.shutdownRootBuffer.clicked.connect(self.action_shutdownRootBuffer)
        self.shutdownAllBuffers.clicked.connect(self.action_shutdownAllBuffers)
        self.killWorkers.clicked.connect(self.action_killWorkers)
        self.exitButton.clicked.connect(self.action_exit)
        self.pauseButton.clicked.connect(self.action_pause)
        
        
        # main tab
        # time active label
        self.time_active_label = self.findChild(QtWidgets.QLabel, "time_active")
        # processes alive label
        self.processes_alive_label = self.findChild(QtWidgets.QLabel, "processes_alive")
        
        
        # TODO
        self.max_number_of_processes = sum(self.infos['workers'][key]['number_of_processes'] for key in self.infos['workers'])

        # table
        self.main_table = self.findChild(QtWidgets.QTableWidget, "main_table")
        self.main_table.setColumnCount(4)
        self.main_table.setRowCount(len(self.infos['roots']))
        self.main_table.setHorizontalHeaderLabels(["Buffer", "Rate (Hz)", "Dead Time (%)", "Number of Events"])
        self.main_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        for i, buffer in enumerate(self.infos['roots']):
            item = QtWidgets.QTableWidgetItem(buffer)
            item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.main_table.setItem(i, 0, item)


    def update_main_table(self, stats: dict):
        for i, buffer in enumerate(self.infos['roots']):
            stat = stats['buffers'][buffer]
            values = [stat["rate"], stat["average_deadtime"], stat["event_count"]]
            for j in range(3):
                item = QtWidgets.QTableWidgetItem(str(values[j]))
                item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                self.main_table.setItem(i, j + 1, item)

    def update_processes_alive(self, stats: dict):
        processes_alive = sum(stats['workers'].values())
        self.processes_alive_label.setText(f"Processes alive: {processes_alive}/{self.max_number_of_processes}")

    def update_time_active(self, stats: dict):
        self.time_active_label.setText(f"Time active: {int(stats['time_active'])}s")

    def update_plots(self):
        try:
            self.stats = self.stats_queue.get_nowait()
        except queue.Empty:
            # If the queue is empty, we can skip this update
            return

        self.rate_canvas.update_plot(self.stats)
        self.process_canvas.update_plot(self.stats)
        self.buffer_canvas.update_plot(self.stats)

        self.update_processes_alive(self.stats)
        self.update_main_table(self.stats)
        self.update_time_active(self.stats)

    def closeEvent(self, event):
        """Handle the window close event."""
        # Replace this with your test condition
        if sum(self.stats['workers'].values()) != 0:
            # Show a warning message
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Warning",
                """Some processes are incomplete. Are you sure you want to exit?
                This will shutdown all buffers and then kill all workers.""",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.No:
                event.ignore()
                return
            self.control.kill_workers()
            # Proceed with closing
            event.accept()

    def action_shutdownRootBuffer(self):
        self.command_queue.put(['buffer', 'roots', 'shutdown'])

    def action_shutdownAllBuffers(self):
        self.command_queue.put(['buffer', 'all', 'shutdown'])

    def action_killWorkers(self):
        self.command_queue.put(['worker', 'all', 'shutdown'])

    def action_exit(self):
        self.close()

    def action_pause(self):
        self.command_queue.put(['buffer', 'roots', 'pause'])
        self.pauseButton.setText("Resume Roots")
        self.pauseButton.clicked.connect(self.action_resume)

    def action_resume(self):
        self.command_queue.put(['buffer', 'roots', 'resume'])
        self.pauseButton.setText("Pause Roots")
        self.pauseButton.clicked.connect(self.action_pause)








class PlotCanvas(FigureCanvas):
    def __init__(self, parent, infos: dict, title=""):
        fig = Figure()
        self.axes = fig.add_subplot(111)
        super().__init__(fig)

        layout = parent.layout()  # Get the existing layout
        if layout is None:
            layout = QtWidgets.QVBoxLayout(parent)
            parent.setLayout(layout)

        layout.addWidget(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Ensure no extra margins
        layout.setSpacing(0)  # Remove extra spacing
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)  # Allow expansion

        self.axes.set_title(title)

        self.buffers = list(infos['buffers'].keys())
        self.workers = list(infos['workers'].keys())
        self.slot_counts = [infos['buffers'][key]['slot_count'] for key in self.buffers]

        self.init_plot()
        fig.tight_layout()


class BufferCanvas(PlotCanvas):
    def init_plot(self):
        x = np.arange(len(self.buffers))
        colors = ["#E24A33", "#FBC15E", "#2CA02C", "#FFFFFF"]
        # colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
        # the ordering of the bars is important
        self.bar_filled = self.axes.bar(x, 0, label="Filled", color=colors[0])
        self.bar_working = self.axes.bar(x, 0, label="Working", color=colors[1])
        self.bar_empty = self.axes.bar(x, 1, label="Empty", color=colors[2])
        self.shutdown_overlay = self.axes.bar(x, 0, label="Shutdown", color=colors[3], alpha=0.3, hatch="//")

        self.axes.set_ylim(0, 1)
        self.axes.legend(loc="upper right")
        self.axes.tick_params(axis="x", rotation=45)
        self.axes.set_ylabel("Ratio")

        self.axes.set_xticks(x)
        self.axes.set_xticklabels(self.buffers)

        xlim = self.axes.get_xlim()
        twiny = self.axes.twiny()
        twiny.set_xticks(x)
        twiny.set_xticklabels(self.slot_counts)
        twiny.set_xlim(xlim)

    def update_plot(self, stats):
        buffer_stats = stats['buffers']
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
        self.bars = self.axes.bar(self.workers, 0, label="Workers", color=colors[0])

        self.resize_axis(1)
        self.axes.tick_params(axis="x", rotation=45)
        for label in self.axes.get_xticklabels():
            label.set_horizontalalignment('right')
        self.axes.set_ylabel("Number of Workers")

    def update_plot(self, stats):
        worker_stats = stats['workers']
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
        self.rates = {key: [0] for key in self.buffers}
        self.times = [0]
        self.lines = {}
        self.init_time = time.time()
        for key in self.buffers:
            self.lines[key] = self.axes.plot(self.times, self.rates[key], label=key)[0]

        self.axes.legend(loc="upper left")
        self.axes.set_ylim(bottom=MIN_RATE)
        self.axes.set_yscale("log")
        self.axes.set_ylabel("Rate (events/s)")
        self.axes.set_xlabel("Time (s)")
        self.axes.grid(True, which='major', alpha=0.9)
        self.axes.grid(True, which='minor', alpha=0.5)
        self.max_y = MIN_RATE

    def update_plot(self, stats):
        buffer_stats = stats['buffers']
        self.times.append(time.time() - self.init_time)
        for key in self.buffers:
            self.rates[key].append(buffer_stats[key]["rate"])
            self.lines[key].set_data(self.times, self.rates[key])
            if self.rates[key][-1] > self.max_y:
                self.max_y = self.rates[key][-1]
                self.axes.set_ylim(top=self.max_y * 1.1)
        self.axes.relim()
        self.axes.autoscale_view()
        self.draw()

def run_gui(command_queue: queue, stats_queue: queue, infos: dict):
    app = QtWidgets.QApplication([])
    window = BufferManagerApp(command_queue, stats_queue, infos)
    window.show()
    app.exec_()