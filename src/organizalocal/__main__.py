"""Permite executar `python -m organizalocal <comando>`."""
import sys

from .cli import main

sys.exit(main())
