import mimocorb2.control as ctrl
import logging
import os
import sys
from mimocorb2.gui import BufferManagerApp
from PyQt5 import QtWidgets

logging.basicConfig(level=logging.INFO)
logging.getLogger('matplotlib').setLevel(logging.WARNING)
logging.getLogger('PyQt5').setLevel(logging.WARNING)

if len(sys.argv) != 2:
    setup_file = "examples/muon/spin_setup.yaml"
    print(f"Using {setup_file}")
else:
    setup_file = sys.argv[1]
reader = ctrl.FileReader(setup_file)
setup = ctrl.SetupRun(reader())
setup_dict = setup()
reader.visualize_setup(file = os.path.join(setup.run_directory, "dataFlow"))
control = ctrl.Control(setup_dict)
control.start_workers()


app = QtWidgets.QApplication(sys.argv)
window = BufferManagerApp(control)
window.show()
sys.exit(app.exec_())
