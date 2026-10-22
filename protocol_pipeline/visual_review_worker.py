# SPDX-License-Identifier: MPL-2.0
"""Detached visual review worker; model/CAD calls never block backend hot reload."""
from pathlib import Path
import logging
import sys
from .web import JobStore
from .visual_review import execute_review

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    store=JobStore(Path(sys.argv[1]),lambda:None)
    try:
        execute_review(store,sys.argv[2],sys.argv[3],sys.argv[4])
    finally:
        store.executor.shutdown()
