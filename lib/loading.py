"""Compatibility entry point without duplicate initialization."""
import settings

def thread_loading():
    return settings.init()
