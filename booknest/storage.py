"""Crash recovery using a write-ahead JSONL transaction journal.

The journal is authoritative. Named JSONL files are rebuildable projections.
A process lock covers reads and writes; interrupted final journal lines are trimmed.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import threading

TABLES = ('users', 'books', 'orders', 'ledger', 'reviews', 'views',
          'moderation_log', 'chat_log', 'progress', 'usage', 'taboo_words')


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._mutex = threading.RLock()
        with self.transaction():
            pass  # Rebuild projections after a crash.

    @contextmanager
    def _lock(self):
        with self._mutex, (self.root / '.lock').open('a+b') as f:
            if os.name == 'nt':
                import msvcrt
                f.seek(0)
                f.write(b'0')
                f.flush()
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'nt':
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(f, fcntl.LOCK_UN)

    def _read(self):
        state = {name: [] for name in TABLES}
        journal = self.root / 'journal.jsonl'
        if not journal.exists():
            return state
        good_end = 0
        with journal.open('rb') as f:
            while line := f.readline():
                # A newline is the commit marker. Never discard corrupt committed data.
                if not line.endswith(b'\n'):
                    break
                entry = json.loads(line)
                for name, rows in entry['replace'].items():
                    state[name] = rows
                for name, rows in entry['append'].items():
                    state[name].extend(rows)
                good_end = f.tell()
        if journal.stat().st_size != good_end:
            with journal.open('r+b') as f:
                f.truncate(good_end)
                f.flush()
                os.fsync(f.fileno())
        return state

    def snapshot(self):
        with self._lock():
            return self._read()

    def _atomic(self, path, body):
        temp = path.with_suffix(path.suffix + '.tmp')
        with temp.open('w', encoding='utf-8') as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)

    @contextmanager
    def transaction(self):
        with self._lock():
            state = self._read()
            before = deepcopy(state)
            yield state
            event = {'replace': {}, 'append': {}}
            for name in TABLES:
                if state[name] == before[name]:
                    continue
                old, new = before[name], state[name]
                if new[:len(old)] == old:
                    event['append'][name] = new[len(old):]
                else:
                    event['replace'][name] = new
            if event['replace'] or event['append']:
                with (self.root / 'journal.jsonl').open('ab') as f:
                    f.write((json.dumps(event, ensure_ascii=False) + '\n').encode())
                    f.flush()
                    os.fsync(f.fileno())
            # Project only changed tables, or all tables on startup/recovery.
            for name in TABLES:
                path = self.root / (name + '.jsonl')
                if state[name] != before[name] or not path.exists() or not (event['replace'] or event['append']):
                    self._atomic(path, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in state[name]))
            self._atomic(self.root / 'taboo_words.txt', '\n'.join(row['word'] for row in state['taboo_words']))
