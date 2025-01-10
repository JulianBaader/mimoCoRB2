import sys
from PyQt5 import QtWidgets, uic, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
import time


WIDTH = 10
HEIGHT = 8
DPI = 100

NUMBER_OF_DATA_POINTS = 10

class BufferManagerApp(QtWidgets.QMainWindow):
    def __init__(self, control):
        super().__init__()
        uic.loadUi("gui.ui", self)
        
        self.control = control
        
        buffers = control.buffers_dict.keys()
        workers = control.functions_dict.keys()

        # Setup matplotlib canvases
        self.rate_canvas = RateCanvas(self.rate_tab, buffers, workers, title="Rate Information")
        self.process_canvas = WorkerCanvas(self.process_tab, buffers, workers, title="Process Information")
        self.buffer_canvas = BufferCanvas(self.buffer_tab, buffers, workers, title="Buffer Information")
    
        

        # Add timers for real-time updates
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plots)
        self.timer.start(2000)  # Update every second

    def update_plots(self):
        buffer_stats = self.control.get_buffer_stats()
        worker_stats = self.control.running_functions()

        self.rate_canvas.update_plot(buffer_stats, worker_stats)
        self.process_canvas.update_plot(buffer_stats, worker_stats)
        self.buffer_canvas.update_plot(buffer_stats, worker_stats)
        
    def closeEvent(self, event):
        """Handle the window close event."""
        # Replace this with your test condition
        if sum(self.control.running_functions().values()) != 0:
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
        # the ordering of the bars is important
        self.bar_filled = self.axes.bar(self.buffers, 0, label="Filled", color="tab:red")
        self.bar_working = self.axes.bar(self.buffers, 0, label="Working", color="tab:blue")
        self.bar_empty = self.axes.bar(self.buffers, 1, label="Empty", color="tab:green")
        
        self.axes.set_ylim(0, 1)
        self.axes.legend(loc = "upper right")
        self.axes.tick_params(axis="x", rotation=45)
        
        
        
    def update_plot(self, buffer_stats, worker_stats):
        filled = np.array([buffer_stats[key]["filled_slots"] for key in self.buffers])
        empty = np.array([buffer_stats[key]["empty_slots"] for key in self.buffers])
        
        for bar, new_height in zip(self.bar_filled, [1] * len(self.buffers)):
            bar.set_height(new_height)
        for bar, new_height in zip(self.bar_working, 1 - filled):
            bar.set_height(new_height)
        for bar, new_height in zip(self.bar_empty, empty):
            bar.set_height(new_height)
        
        self.draw()
        
class WorkerCanvas(PlotCanvas):
    def init_plot(self):
        self.bars = self.axes.bar(self.workers, 0, label="Workers", color="tab:blue")
        
        self.resize_axis(1)
        self.axes.tick_params(axis="x", rotation=45)
        for label in self.axes.get_xticklabels():
            label.set_horizontalalignment('right')
        
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
        self.rates = {key: [0]*NUMBER_OF_DATA_POINTS for key in self.buffers}
        self.last_event_count = {key: 0 for key in self.buffers}
        self.last_update_time = {key: time.time() for key in self.buffers}
        self.lines = {}
        for key in self.buffers:
            self.lines[key] = self.axes.plot()
        self.lines = {key: self.axes.plot(np.arange(-NUMBER_OF_DATA_POINTS, 0) + 1, self.rates[key], label=key)[0] for key in self.buffers}
        
        self.axes.legend(loc="upper left")
        self.axes.set_ylim(.1, 2000)
        self.axes.set_yscale("log")
        for label in self.axes.get_xticklabels():
            label.set_horizontalalignment('right')
        
    def update_plot(self, buffer_stats, worker_stats):
        for key in self.buffers:
            event_count = buffer_stats[key]["event_count"]
            update_time = time.time()
            
            rate = (event_count - self.last_event_count[key]) / (update_time - self.last_update_time[key])
            if key == 'raw_osc':
                print(rate)
            self.rates[key].append(rate)
            self.rates[key].pop(0)

            
            self.last_event_count[key] = event_count
            self.last_update_time[key] = update_time
            
            self.lines[key].set_ydata(self.rates[key])
            
        #self.axes.relim()
        #self.axes.autoscale_view()
        #self.axes.set_ylim(bottom=0)
        self.draw()
            


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = BufferManagerApp()
    window.show()
    sys.exit(app.exec_())
