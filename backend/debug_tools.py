import traceback
import sys
import datetime

def log_debug(msg):
    with open("backend_debug_log.txt", "a", encoding="utf-8") as f:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {msg}\n")

def log_exception(e, context=""):
    msg = f"EXCEPTION in {context}: {str(e)}\n{traceback.format_exc()}"
    log_debug(msg)
