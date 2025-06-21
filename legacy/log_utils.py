import builtins
import datetime as _dt
import os as _os

_original_print = builtins.print


def _patched_print(*args, **kwargs):
    """Replacement for built-in print that adds timestamp & PID prefix.

    Format: 2025-06-14 12:34:56 [12345] <message>
    If the first argument starts with a carriage return ("\r"), the prefix is
    injected *after* the return so that progress bars keep overwriting the
    same line.
    """
    # Build prefix
    prefix = f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S} [PID {_os.getpid()}]"

    if args and isinstance(args[0], str) and args[0].startswith("\r"):
        # Preserve carriage return at the start for progress updates
        first = f"\r{prefix} {args[0][1:]}"
        new_args = (first, *args[1:])
    else:
        new_args = (prefix, *args)

    # Ensure flushing unless explicitly disabled
    if "flush" not in kwargs:
        kwargs["flush"] = True

    _original_print(*new_args, **kwargs)


# Apply the monkey patch only once
builtins.print = _patched_print 