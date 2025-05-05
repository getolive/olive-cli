import threading

# Global event for manual Ctrl+C pause/resume handling
_INTERRUPTED = threading.Event()
