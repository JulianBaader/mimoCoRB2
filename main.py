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

while sum(control.running_functions().values()) != 0:
    print(control.get_buffer_stats())
    time.sleep(1)
    
print("No more functions are running")