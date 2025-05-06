import mimocorb2.control as ctrl
import logging
import os
import sys
from mimocorb2.gui import BufferManagerApp
from PyQt5 import QtWidgets
import matplotlib.pyplot as plt

# plt.style.use('dark_background')

logging.basicConfig(level=logging.INFO)
logging.getLogger('matplotlib').setLevel(logging.WARNING)
logging.getLogger('PyQt5').setLevel(logging.WARNING)

if len(sys.argv) != 2:
    setup_file = "examples/muon/spin_setup.yaml"
    print(f"Using {setup_file}")
else:
    setup_file = sys.argv[1]


control = ctrl.Control(setup_file)
control.start_workers()


app = QtWidgets.QApplication(sys.argv)
try:
    window = BufferManagerApp(control)
except Exception as e:
    control.kill_workers()
    raise e
window.show()
sys.exit(app.exec_())
