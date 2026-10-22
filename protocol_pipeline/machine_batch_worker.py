# SPDX-License-Identifier: MPL-2.0
"""Run Forma jobs outside the web/reloader process while persisting the same machine states."""
import logging
import json
from pathlib import Path
import sys
import time

from .web import JobStore

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    store = JobStore(Path(sys.argv[1]), lambda: None)
    store.slots.acquire()
    try:
        store.execute_machines(sys.argv[2], sys.argv[3:])
    finally:
        first = json.loads((store.path(sys.argv[2]) / 'machines' / sys.argv[3] / 'job.json').read_text(encoding='utf-8'))
        status = store.path(sys.argv[2]) / 'machines/batches' / first['batch_id'] / 'worker.json'
        if status.is_file():
            value = json.loads(status.read_text(encoding='utf-8'))
            value.update(stage='finished', finished_at=time.time())
            status.with_suffix('.tmp').write_text(json.dumps(value), encoding='utf-8')
            status.with_suffix('.tmp').replace(status)
        store.executor.shutdown()
