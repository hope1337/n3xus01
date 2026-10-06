"""Transient terminal feedback only; never a daemon or a JSON transport."""
from contextlib import contextmanager, redirect_stdout
import copy
import io
import shutil
import sys
import threading
from device_ui import UI, crop, sanitize, width

_active = None

class Progress:
    def __init__(self, color, renderer=None):
        self.ui = UI(color)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.operations = []
        self.snapshot = None
        self.lines = 0
        self.tick = 0
        self.renderer = renderer

    def clear(self):
        if self.renderer is not None:
            return  # Full-screen owner replaces its own frame at the origin.
        if self.lines:
            sys.stdout.write(f'\033[{self.lines}F\033[J')
            self.lines = 0
            sys.stdout.flush()

    def draw(self):
        with self.lock:
            if self.renderer is not None:
                frame = io.StringIO()
                with redirect_stdout(frame):
                    self.renderer(self.snapshot,'|/-\\'[self.tick % 4])
                sys.stdout.write(frame.getvalue())
                sys.stdout.flush()
                self.tick += 1
                return
            self.clear()
            if not self.operations and self.snapshot is None:
                return
            frame = io.StringIO()
            if self.snapshot is not None:
                frame.write(self.snapshot)
            label = self.operations[-1] if self.operations else 'Waiting for remaining results'
            frame.write(self.ui.paint(crop('|/-\\'[self.tick % 4] + ' ' + label + ' ...', self.ui.columns), '33') + '\n')
            lines = frame.getvalue().splitlines()
            height = max(3, shutil.get_terminal_size((110,24)).lines - 2)
            if len(lines) > height:
                lines = lines[:height-2] + ['… more results will appear in the completed view', lines[-1]]
            text = '\n'.join(lines) + '\n'
            sys.stdout.write(text)
            sys.stdout.flush()
            columns = max(1, shutil.get_terminal_size((110,24)).columns)
            self.lines = sum(max(1,(width(sanitize(line))+columns-1)//columns) for line in lines)
            self.tick += 1

    def loop(self):
        while not self.stop.wait(.15):
            self.draw()

    def publish(self, action, data):
        # Collectors and streamed RPC readers publish under the display lock.
        with self.lock:
            if self.renderer is not None:
                self.snapshot = (action,copy.deepcopy(data))
                self.draw()
                return
            frame = io.StringIO()
            with redirect_stdout(frame):
                self.ui.render(action, data)
            self.snapshot = frame.getvalue()
            self.draw()


def publish(action, data):
    if _active is not None:
        _active.publish(action, data)

def enabled():
    return _active is not None


@contextmanager
def operation(label, clear_snapshot=False):
    progress = _active
    if progress is None:
        yield
        return
    label = sanitize(label).replace('\n',' ')
    with progress.lock:
        progress.operations.append(label)
        progress.draw()
    try:
        yield
    finally:
        with progress.lock:
            progress.operations.remove(label)
            if clear_snapshot:
                progress.snapshot = None
            if not progress.operations and progress.snapshot is None:
                progress.clear()


@contextmanager
def terminal(color='auto', enabled=True, renderer=None):
    global _active
    if not enabled or not sys.stdout.isatty() or _active is not None:
        yield
        return
    progress = Progress(color,renderer)
    _active = progress
    thread = threading.Thread(target=progress.loop, name='terminal-feedback', daemon=True)
    thread.start()
    try:
        yield
    finally:
        progress.stop.set()
        thread.join()
        with progress.lock:
            progress.clear()
        _active = None
