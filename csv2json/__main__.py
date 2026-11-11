"""Allow ``python -m csv2json``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
