import json
from decimal import Decimal, ROUND_HALF_UP
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from tkinter import font as tkfont
from .ai import Assistant


class App(tk.Tk):
    def __init__(self, service):
        super().__init__()
        self.svc = service
        self.ai = Assistant(service)
        self.title('BookNest • Your local reading room')
        self.geometry('1180x800')
        self.minsize(900, 640)
        self.cart = []
        self.messages = queue.Queue()
        self.busy = False
        self.displayed_user = None
        self.page = 0
        self.picture = ''
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TButton', padding=7)
        style.configure('Treeview', rowheight=30)
        header = ttk.Frame(self, padding=16)
        header.pack(fill='x')
        ttk.Label(header, text='BookNest', font=('TkDefaultFont', 24, 'bold')).pack(side='left')
        ttk.Label(header, text='  A local home for books & ideas').pack(side='left')
        self.identity = ttk.Label(header)
        self.identity.pack(side='right')
        controls = ttk.Frame(self, padding=(16, 0))
        controls.pack(fill='x')
        for label, action in [('Join BookNest', self.register), ('Face login', self.login),
                              ('Admin recovery', self.recovery), ('Log out', self.logout)]:
            ttk.Button(controls, text=label, command=self.guard(action)).pack(side='left', padx=(0, 6))
        ttk.Button(controls, text='Font +', command=lambda: self.resize_font(1)).pack(side='right')
        ttk.Button(controls, text='Font −', command=lambda: self.resize_font(-1)).pack(side='right')
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True, padx=16, pady=12)
        self.frames = {}
        for name in ('Home', 'Catalog', 'Cart', 'My Account', 'Assistant', 'SU Console'):
            frame = ttk.Frame(self.tabs, padding=12)
            self.tabs.add(frame, text=name)
            self.frames[name] = frame
        self.status = tk.StringVar(value='Ready • Local text-file storage')
        ttk.Label(self, textvariable=self.status, padding=(16, 6)).pack(fill='x')
        # Some fixed tabs
        self.make_catalog()
        self.make_chat()
        self.make_admin()
        self.refresh()
        # Timers
        self.after(100, self.poll)
        self.after(30_000, self.idle_check)
        self.after(300, self.first_run)

# Error Handling | Background Work
# Helps ensurs responsitivity 
    def destroy(self):
        # Cancel scheduled Tcl callbacks before destroying their Python commands.
        for callback in self.tk.call('after', 'info'):
            self.after_cancel(callback)
        super().destroy()

    def guard(self, function):
        def run(*args):
            if self.busy:
                self.status.set('Please wait for the current operation to finish.')
                return
            try:
                return function(*args)
            except Exception as exc:
                messagebox.showerror('BookNest', str(exc), parent=self)
        return run

    def worker(self, task, done=None):
        if self.busy:
            return
        self.busy = True
        self.status.set('Working… Camera windows may open separately; ESC cancels capture.')
        def run():
            try:
                result = task()
                self.messages.put(('result', (done, result)))
            except Exception as exc:
                self.messages.put(('error', str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, data = self.messages.get_nowait()
                if kind == 'confirm':
                    name, distance, event, answer = data
                    answer.append(messagebox.askyesno('Confirm identity', f'Is this you: {name}?\nRecognition distance: {distance:.1f}', parent=self))
                    event.set()
                else:
                    self.busy = False
                    self.status.set('Ready')
                    if kind == 'error':
                        messagebox.showerror('BookNest', data, parent=self)
                    else:
                        callback, result = data
                        if callback:
                            callback(result)
                    self.refresh()
        except queue.Empty:
            pass
        self.after(100, self.poll)

# Accesibility feature and activity monitors
    def idle_check(self):
        # Reading identity here would refresh the session; inspect idle time separately.
        import time
        from .config import IDLE_SECONDS
        if not self.busy and self.svc.session._user_id and time.monotonic() - self.svc.session.touched > IDLE_SECONDS:
            self.svc.session.logout()
            self.cart.clear()
            self.refresh()
            self.status.set('Logged out after 15 minutes of inactivity.')
        self.after(30_000, self.idle_check)

    def resize_font(self, delta):
        font = tkfont.nametofont('TkDefaultFont')
        font.configure(size=max(9, min(20, font.cget('size') + delta)))

    def first_run(self):
        if not any(u['role'] == 'SU' for u in self.svc.store.snapshot()['users']):
            secret = simpledialog.askstring('First-run setup', 'Create the administrator recovery passphrase (12+ characters).\nStore it safely; it is never displayed again.', show='*', parent=self)
            if secret:
                try:
                    self.svc.setup_admin(secret)
                    messagebox.showinfo('BookNest', 'Administrator created. Use Admin recovery to log in and enroll a face.', parent=self)
                except ValueError as exc:
                    messagebox.showerror('BookNest', str(exc), parent=self)
                    self.after(200, self.first_run)

    def clear(self, frame):
        for child in frame.winfo_children():
            child.destroy()

# Authentication aspects - facial rec login 
    def register(self):
        values = self.form('Join BookNest', [('username', 'Username', ''), ('name', 'Display name', ''), ('deposit', 'Opening deposit ($)', '25.00')])
        if values:
            messagebox.showinfo('Face enrollment', 'Your face images will be stored only on this computer.\nMove gently left/right and look up/down during capture.\nContinue only if you consent. ESC cancels.', parent=self)
            self.worker(lambda: self.svc.register(values['username'], values['name'], values['deposit']))

    def login(self):
        def confirm(name, distance):
            event, answer = threading.Event(), []
            self.messages.put(('confirm', (name, distance, event, answer)))
            event.wait()
            return answer[0]
        self.worker(lambda: self.svc.login_face(confirm))

    def recovery(self):
        secret = simpledialog.askstring('Administrator recovery', 'Recovery passphrase:', show='*', parent=self)
        if secret:
            self.worker(lambda: self.svc.recover_admin(secret))

    def logout(self):
        self.svc.session.logout()
        self.cart.clear()
        self.chat_output.delete('1.0', 'end')
        self.refresh()

    def form(self, title, fields, files=None):
        window = tk.Toplevel(self)
        window.title(title)
        window.transient(self)
        variables, result = {}, {}
        for i, (key, label, default) in enumerate(fields):
            ttk.Label(window, text=label).grid(row=i, column=0, sticky='w', padx=12, pady=6)
            var = tk.StringVar(value=default)
            variables[key] = var
            ttk.Entry(window, textvariable=var, width=48).grid(row=i, column=1, padx=12)
            if files and key in files:
                def pick(v=var):
                    path = filedialog.askopenfilename(parent=window)
                    if path:
                        v.set(path)
                ttk.Button(window, text='Browse', command=pick).grid(row=i, column=2, padx=8)
        def save():
            result.update({k: v.get() for k, v in variables.items()})
            window.destroy()
        ttk.Button(window, text='Continue', command=save).grid(row=len(fields), column=1, pady=12, sticky='e')
        window.grab_set()
        self.wait_window(window)
        return result
