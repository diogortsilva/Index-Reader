"""Entry point of the packaged Windows program (Index-Reader.exe)."""

import sys

from index_reader.cli import main

if __name__ == "__main__":
    sys.exit(main())
