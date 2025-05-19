from PyQt5 import QtWidgets, uic, QtCore
from mimocorb2.control import Control
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import multiprocessing as mp
import time
import numpy as np
import os
import matplotlib

# Rate Config
MIN_RATE = 0.1
MAX_RATE = 250.0
TIME_RATE = 60

# Buffer Config
BUFFER_COLORS = ["#E24A33", "#FBC15E", "#2CA02C", "#FFFFFF"]

def get_infos_from_control(control: Control):
    """
    Get the information from the control object.
    """
    buffers = {name: {'slot_count': buffer.slot_count} for name, buffer in control.buffers.items()}
    workers = {name: {'number_of_processes': worker.number_of_processes} for name, worker in control.workers.items()}
    roots = list(control.roots.keys())
    return {'buffers': buffers, 'workers': workers, 'roots': roots}

def run_gui(command_queue: mp.Queue, stats_queue: mp.Queue, infos: dict):
    app = QtWidgets.QApplication([])
    window = ControlGui(command_queue, stats_queue, infos)
    window.show()
    app.exec_()

class ControlGui(QtWidgets.QMainWindow):
    def __init__(self, command_queue: mp.Queue, stats_queue: mp.Queue, infos: dict):
        super().__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), "gui.ui"), self)
        self.command_queue = command_queue
        self.stats_queue = stats_queue
        self.infos = infos
        
        self.rate_plot = RatePlot(self.infos, self, "ratePlaceholder")
        self.worker_plot = WorkerPlot(self.infos, self, "workerPlaceholder")
        self.buffer_plot = BufferPlot(self.infos, self, "bufferPlaceholder")
        self.table = Table(self.infos, self, "tablePlaceholder")
        self.buttons = Buttons(self.command_queue, self)
        self.status_bar = StatusBar(self)
        
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_gui)
        self.timer.start(1000)  # Update every second
        
    def update_gui(self):
        """
        Update the GUI with the latest stats.
        """
        try:
            stats = self.stats_queue.get_nowait()
            self.rate_plot.update_plot(stats)
            self.buffer_plot.update_plot(stats)
            self.worker_plot.update_plot(stats)
            self.table.update_table(stats)
            self.status_bar.update_status(stats)
        except mp.queues.Empty:
            pass

class MplCanvas(FigureCanvas):
    def __init__(self, infos: dict, parent=None, placeholder_name: str = None):
        self.fig = Figure()
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.infos = infos
        self.buffer_names = list(infos['buffers'].keys())
        self.worker_names = list(infos['workers'].keys())

        # If a placeholder name is given, find and set it up
        if placeholder_name and parent:
            rateWidget_placeholder = parent.findChild(QtWidgets.QWidget, placeholder_name)
            if rateWidget_placeholder:
                layout = QtWidgets.QVBoxLayout(rateWidget_placeholder)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.addWidget(self)
                
        
        
class RatePlot(MplCanvas):
    def __init__(self, infos: dict, parent=None, placeholder_name: str = None):
        super().__init__(infos, parent, placeholder_name)
        self.axes.set_title("Rate")
        self.axes.set_xlabel("Time (s)")
        self.axes.set_ylabel("Rate (Hz)")
        
        self.xdata = [-TIME_RATE, 0]
        self.ydatas = {name: [0, 0] for name in self.buffer_names}
        self.axes.set_xlim(-TIME_RATE, 0)
        self.axes.set_ylim(MIN_RATE, MAX_RATE)
        
        self.lines = {name: self.axes.plot(self.xdata, self.ydatas[name], label=name)[0] for name in self.buffer_names}
        self.axes.legend(loc="upper left")
        self.axes.set_yscale("log")
        self.axes.grid(True, which='major', alpha=0.9)
        self.axes.grid(True, which='minor', alpha=0.5)
        
        self.fig.tight_layout()
        self.draw()

        
    def update_plot(self, stats):
        time_active = stats['time_active']

        self.xdata.append(time_active)
        
        while self.xdata and self.xdata[0] < time_active - TIME_RATE:
            self.xdata.pop(0)

        shifted_x = [x - time_active for x in self.xdata]

        for name in self.buffer_names:
            self.ydatas[name].append(stats['buffers'][name]['rate'])
            while len(self.ydatas[name]) > len(self.xdata):
                self.ydatas[name].pop(0)

            self.lines[name].set_xdata(shifted_x)
            self.lines[name].set_ydata(self.ydatas[name])
        
        self.draw()
        
class WorkerPlot(MplCanvas):
    def __init__(self, infos: dict, parent=None, placeholder_name: str = None):
        super().__init__(infos, parent, placeholder_name)
        number_of_processes = [infos['workers'][name]['number_of_processes'] for name in self.worker_names]
        self.axes.grid(True, which='major', alpha=0.9, axis='y')
        self.axes.bar(self.worker_names, number_of_processes)
        
        self.axes.tick_params(axis="x", rotation=45)
        for label in self.axes.get_xticklabels():
            label.set_horizontalalignment('right')
        self.axes.set_ylabel("Number of Workers")
        self.axes.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        
        
        self.fig.tight_layout()
        self.draw()
        
    def update_plot(self, stats):
        number_of_processes = [stats['workers'][name]['number_of_processes'] for name in self.worker_names]
        for bar, new_height in zip(self.axes.patches, number_of_processes):
            bar.set_height(new_height)
        self.draw()
        
class BufferPlot(MplCanvas):
    def __init__(self, infos: dict, parent=None, placeholder_name: str = None):
        super().__init__(infos, parent, placeholder_name)
        x = np.arange(len(self.buffer_names))
        
        # the ordering of the bars is important
        self.bar_filled = self.axes.bar(x, 0, label="Filled", color=BUFFER_COLORS[0])
        self.bar_working = self.axes.bar(x, 0, label="Working", color=BUFFER_COLORS[1])
        self.bar_empty = self.axes.bar(x, 1, label="Empty", color=BUFFER_COLORS[2])
        self.shutdown_overlay = self.axes.bar(x, 0, label="Shutdown", color=BUFFER_COLORS[3], alpha=0.3, hatch="//")

        self.axes.set_ylim(0, 1)
        self.axes.legend(loc="upper right")
        self.axes.tick_params(axis="x", rotation=45)
        self.axes.set_ylabel("Ratio")

        self.axes.set_xticks(x)
        self.axes.set_xticklabels(self.buffer_names)

        xlim = self.axes.get_xlim()
        twiny = self.axes.twiny()
        twiny.set_xticks(x)
        
        slot_counts = [infos['buffers'][name]['slot_count'] for name in self.buffer_names]
        
        twiny.set_xticklabels(slot_counts)
        twiny.set_xlim(xlim)
        self.fig.tight_layout()
        
    def update_plot(self, stats):
        buffer_stats = stats['buffers']
        filled = np.array([buffer_stats[key]["filled_slots"] for key in self.buffer_names])
        empty = np.array([buffer_stats[key]["empty_slots"] for key in self.buffer_names])
        shutdown = np.array([buffer_stats[key]["flush_event_received"] for key in self.buffer_names])

        self._set_heights(self.bar_filled, [1] * len(self.buffer_names))
        self._set_heights(self.bar_working, 1 - filled)
        self._set_heights(self.bar_empty, empty)
        self._set_heights(self.shutdown_overlay, shutdown)
        self.draw()
        
    def _set_heights(self, bars, new_heights):
        for bar, new_height in zip(bars, new_heights):
            bar.set_height(new_height)
        

class Table:
    def __init__(self, infos: dict, parent, widget_name: str):
        self.table = parent.findChild(QtWidgets.QTableWidget, widget_name)
        self.infos = infos

        self.table.setColumnCount(4)
        self.table.setRowCount(len(infos['roots']))
        self.table.setHorizontalHeaderLabels(["Buffer", "Rate (Hz)", "Dead Time (%)", "Number of Events"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        for i, buffer in enumerate(self.infos['roots']):
            item = QtWidgets.QTableWidgetItem(buffer)
            item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.table.setItem(i, 0, item)
            
    def update_table(self, stats):
        for i, buffer in enumerate(self.infos['roots']):
            buffer_stats = stats['buffers'][buffer]
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(f"{buffer_stats['rate']:.2f}"))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(f"{buffer_stats['average_deadtime']:.2f}"))
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(str(buffer_stats['event_count'])))
            

class Buttons:
    def __init__(self, command_queue: mp.Queue, parent):
        self.command_queue = command_queue
        self.parent = parent

        self.pause_resume_RootBuffersButton = parent.findChild(QtWidgets.QPushButton, "pause_resume_RootBuffersButton")
        self.shutdownRootBuffersButton = parent.findChild(QtWidgets.QPushButton, "shutdownRootBuffersButton")
        self.shutdownAllBuffersButton = parent.findChild(QtWidgets.QPushButton, "shutdownAllBuffersButton")
        self.shutdownAllWorkersButton = parent.findChild(QtWidgets.QPushButton, "shutdownAllWorkersButton")
        
        self.pause_resume_Root_status = 'resume'
        
        self.pause_resume_RootBuffersButton.clicked.connect(self.action_pause_resume_root_buffers)
        self.shutdownRootBuffersButton.clicked.connect(self.action_shutdown_root_buffers)
        self.shutdownAllBuffersButton.clicked.connect(self.action_shutdown_all_buffers)
        self.shutdownAllWorkersButton.clicked.connect(self.action_shutdown_all_workers)

        
    def action_shutdown_root_buffers(self):
        self.command_queue.put(['buffer', 'roots', 'shutdown'])
        
    def action_shutdown_all_buffers(self):
        self.command_queue.put(['buffer', 'all', 'shutdown'])
        
    def action_shutdown_all_workers(self):
        self.command_queue.put(['worker', 'all', 'shutdown'])
        
    def action_pause_resume_root_buffers(self):
        if self.pause_resume_Root_status == 'resume':
            self.command_queue.put(['buffer', 'roots', 'pause'])
            self.pause_resume_RootBuffersButton.setText("Resume Roots")
            self.pause_resume_Root_status = 'pause'
        else:
            self.command_queue.put(['buffer', 'roots', 'resume'])
            self.pause_resume_RootBuffersButton.setText("Pause Roots")
            self.pause_resume_Root_status = 'resume'

class StatusBar:
    def __init__(self, parent):
        self.parent = parent
        self.timeActiveLabel = parent.findChild(QtWidgets.QLabel, "timeActiveLabel")
        self.processesAliveLabel = parent.findChild(QtWidgets.QLabel, "processesAliveLabel")
        
    def update_status(self, stats):
        time_active = stats['time_active']
        self.timeActiveLabel.setText(f"Time Active: {time_active:.2f} s")
        
        processes_alive = sum(stats['workers'][name]['number_of_processes'] for name in stats['workers'])
        self.processesAliveLabel.setText(f"Processes Alive: {processes_alive}")
        
if __name__ == '__main__':
    infos = {'buffers': {'InputBuffer': {'slot_count': 128}, 'AcceptedPulses': {'slot_count': 128}, 'PulseParametersUp': {'slot_count': 32}, 'PulseParametersDown': {'slot_count': 32}, 'PulseParametersUp_Export': {'slot_count': 32}, 'PulseParametersDown_Export': {'slot_count': 32}}, 'workers': {'input': {'number_of_processes': 1}, 'filter': {'number_of_processes': 3}, 'save_pulses': {'number_of_processes': 1}, 'histUp': {'number_of_processes': 1}, 'histDown': {'number_of_processes': 1}, 'saveUp': {'number_of_processes': 1}, 'saveDown': {'number_of_processes': 1}, 'oscilloscope': {'number_of_processes': 1}, 'accepted_ocilloscope': {'number_of_processes': 1}}, 'roots': ['InputBuffer']}
    buffer_example = {
        'event_count': 0,
        'filled_slots': 0.0,
        'empty_slots': 0.984375,
        'flush_event_received': False,
        'rate': 127.95311213377948,
        'average_deadtime': 0.08628888769168282,
        'paused_count': 0,
        'paused': False
    }
    worker_example = {
        'number_of_processes': 1
    }
    
    stats = {
        'buffers': {
            'InputBuffer': buffer_example.copy(),
            'AcceptedPulses': buffer_example.copy(),
            'PulseParametersUp': buffer_example.copy(),
            'PulseParametersDown': buffer_example.copy(),
            'PulseParametersUp_Export': buffer_example.copy(),
            'PulseParametersDown_Export': buffer_example.copy()
        },
        'workers': {
            'input': worker_example.copy(),
            'filter': worker_example.copy(),
            'save_pulses': worker_example.copy(),
            'histUp': worker_example.copy(),
            'histDown': worker_example.copy(),
            'saveUp': worker_example.copy(),
            'saveDown': worker_example.copy(),
            'oscilloscope': worker_example.copy(),
            'accepted_ocilloscope': worker_example.copy()
        },
        'time_active': 0
    }
    def update_stats(stats):
        """
        Update the stats with random values for testing.
        """
        for buffer in stats['buffers'].values():
            buffer['rate'] = np.random.uniform(MIN_RATE, MAX_RATE)
            empty = np.random.uniform(0, 1)
            filled = np.random.uniform(0, 1-empty)
            buffer['filled_slots'] = filled
            buffer['empty_slots'] = empty
            buffer['event_count'] += np.random.randint(0, 1000)
            buffer['average_deadtime'] = np.random.uniform(0, 1)
        for worker in stats['workers'].values():
            worker['number_of_processes'] = np.random.randint(1, 5)
        return stats

    
    command_queue = mp.Queue()
    stats_queue = mp.Queue(1)
    
    # Start the GUI in a separate process
    gui_process = mp.Process(target=run_gui, args=(command_queue, stats_queue, infos))
    gui_process.start()
    # Simulate sending stats to the GUI
    last_stats = time.time()
    start_time = time.time()
    while True:
        try:
            print(command_queue.get_nowait())
        except mp.queues.Empty:
            pass
        if time.time() - last_stats > 1:
            last_stats = time.time()
            stats = update_stats(stats)
            stats['time_active'] = time.time() - start_time
            stats_queue.put(stats)
        # Check if the GUI process is still alive
        if not gui_process.is_alive():
            break
