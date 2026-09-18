"""PyInstaller belépési pont."""
import multiprocessing
import sys

from osintdd.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
