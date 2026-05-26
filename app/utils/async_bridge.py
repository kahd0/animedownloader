import asyncio
import threading

from PySide6.QtCore import QObject, Signal, Qt

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


class _Bridge(QObject):
    _callback_ready = Signal(object, object)

    def __init__(self):
        super().__init__()
        self._callback_ready.connect(self._dispatch, Qt.QueuedConnection)

    def _dispatch(self, callback, result):
        if callback:
            try:
                callback(result)
            except Exception:
                import traceback
                traceback.print_exc()


_bridge: _Bridge | None = None


def _get_bridge() -> "_Bridge":
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()
    return _bridge


def run_async(coro, on_done=None):
    bridge = _get_bridge()  # must be captured on the main Qt thread

    def _callback(future):
        try:
            result = future.result()
        except Exception as e:
            result = e
        bridge._callback_ready.emit(on_done, result)

    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    future.add_done_callback(_callback)
    return future


def stop_loop():
    if _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)


def get_event_loop():
    return _loop


# Legacy compat — no-op in PySide6 (app ref not needed)
def set_app_ref(app):
    pass
