import mimocorb2.control as ctrl
import logging
import sys

# plt.style.use('dark_background')

logging.basicConfig(level=logging.INFO)
logging.getLogger('matplotlib').setLevel(logging.WARNING)
logging.getLogger('PyQt5').setLevel(logging.WARNING)

if len(sys.argv) != 2:
    setup_file = "examples/muon/spin_setup.yaml"
    print(f"Using {setup_file}")
else:
    setup_file = sys.argv[1]


control = ctrl.Control(setup_file, mode='gui')
control()
