from mimocorb2.control import mimoControl, fileReader
import logging
import sys
import time
from mimocorb2.gui import BufferManagerApp
from PyQt5 import QtWidgets

logging.basicConfig(level=logging.INFO)

reader = fileReader(sys.argv[1])
control = mimoControl(*reader())
if not control.check_data_flow():
    raise ValueError("Data flow is not correct")
control.visualize_buffers_and_functions()
control.initialize_buffers()
control.initialize_functions()
control.start_functions()


app = QtWidgets.QApplication(sys.argv)
window = BufferManagerApp(control)
window.show()
sys.exit(app.exec_())