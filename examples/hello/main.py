import os
from pathlib import Path
import platform
import time

print('Hello from', platform.node(), flush=True)
for step in range(3):
    print('Step', step + 1, flush=True)
    time.sleep(1)
output = Path(os.environ['DEVICE_OUTPUT_DIR'])
(output / 'hello.txt').write_text('Code ran directly on the device. No container.\n', encoding='utf-8')
print('Result:', output / 'hello.txt', flush=True)
