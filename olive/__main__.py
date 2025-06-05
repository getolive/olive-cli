# cli/olive/__main__.py

import atexit
import signal

from olive.cli import app
from olive.sandbox import sandbox

atexit.register(sandbox.stop)
signal.signal(signal.SIGTERM, lambda *_: sandbox.stop())

if __name__ == "__main__":
    app()
