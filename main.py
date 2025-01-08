from mimocorb2.control import mimoControl, fileReader
import logging
import sys
import time

logging.basicConfig(level=logging.INFO)

reader = fileReader(sys.argv[1])
control = mimoControl(*reader())
if not control.check_data_flow():
    raise ValueError("Data flow is not correct")

control.initialize_buffers()
control.initialize_functions()
control.start_functions()

while True:
    stats = control.get_stats()
    print(stats)
    time.sleep(1)