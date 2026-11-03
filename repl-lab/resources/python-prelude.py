# Helpers loaded into every Python worker of the assisted surface (the Python
# counterpart of resources/sci-prelude.edn). Printed output and result display
# live in the worker itself (worker/src/repl_lab/python_worker.py).
def page(v, offset=0, n=24000):
    """n characters of v's text (a string as is, anything else by repr) from offset; stops at the end."""
    text = v if isinstance(v, str) else repr(v)
    start = max(0, min(offset, len(text)))
    return text[start:start + max(0, n)]


last_result = None
full_result = None
