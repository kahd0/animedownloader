import asyncio
import threading

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

app_ref = None

def set_app_ref(app):
    global app_ref
    app_ref = app

def stop_loop():
    if _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)

def run_async(coro, on_done=None):
    def _callback(future):
        try:
            result = future.result()
        except Exception as e:
            result = e
            if not on_done and app_ref:
                app_ref.after(0, lambda exc=e: _report_unhandled(exc))
        if on_done and app_ref:
            app_ref.after(0, lambda: on_done(result))

    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    future.add_done_callback(_callback)
    return future

def _report_unhandled(exc: Exception):
    if not app_ref:
        return
    try:
        from app.ui.dialogs.error_reporter import show_error_dialog
        show_error_dialog(app_ref, exc, "Erro em operação assíncrona")
    except Exception:
        import traceback
        traceback.print_exc()

def get_event_loop():
    return _loop
