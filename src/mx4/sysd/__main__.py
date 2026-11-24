"""Entry point: ``python -m mx4.sysd`` / the ``mx4-sysd`` console script."""

from __future__ import annotations

import sys

from .service import main

if __name__ == "__main__":
    sys.exit(main())
