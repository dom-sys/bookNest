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

# Refresh - syncs the whole UI with the current state
    def refresh(self):
        user = self.svc.me()
        uid = user['id'] if user else None
        if self.displayed_user != uid:
            self.cart.clear()
            self.chat_output.delete('1.0', 'end')
            for child in self.winfo_children():
                if isinstance(child, tk.Toplevel):
                    child.destroy()
            self.displayed_user = uid
        self.identity.configure(text=f"{user['name']} • {user['role']} • {self.svc.dollars(user['balance'])}" if user else 'Visitor • Browse freely')
        self.tabs.tab(self.frames['SU Console'], state='normal' if user and user['role'] == 'SU' else 'hidden')
        self.render_home()
        self.search()
        self.render_cart()
        self.render_account()

# The following are for tabs, their content, and interaction with the service layer
    def render_home(self):
        frame = self.frames['Home']
        self.clear(frame)
        ttk.Label(frame, text='Your next chapter', font=('TkDefaultFont', 22, 'bold')).pack(anchor='w', pady=(0, 8))
        ttk.Label(frame, text='Three recommendations based on your reading history, or what is popular in the store.').pack(anchor='w')
        for book, reason in self.svc.recommendations():
            card = ttk.LabelFrame(frame, text=book['category'], padding=14)
            card.pack(fill='x', pady=8)
            ttk.Label(card, text=book['title'], font=('TkDefaultFont', 16, 'bold')).pack(anchor='w')
            rating, count = self.svc.rating(self.svc.store.snapshot(), book['id'])
            ttk.Label(card, text=f"{book['author']} • {self.svc.dollars(book['price'])} • {rating:.1f}/5 ({count})").pack(anchor='w')
            ttk.Label(card, text=reason).pack(anchor='w', pady=4)
            ttk.Button(card, text='Explore book', command=self.guard(lambda bid=book['id']: self.detail(bid))).pack(anchor='e')

    def make_catalog(self):
        frame = self.frames['Catalog']
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        self.filters = {}
        for key, label, width in [('query', 'Keywords', 24), ('category', 'Category', 14), ('author', 'Author', 14), ('year', 'Year prefix', 9)]:
            ttk.Label(bar, text=label).pack(side='left', padx=3)
            var = tk.StringVar()
            self.filters[key] = var
            entry = ttk.Entry(bar, textvariable=var, width=width)
            entry.pack(side='left')
            entry.bind('<Return>', self.guard(lambda e: self.new_search()))
        self.sort = tk.StringVar(value='title')
        ttk.Combobox(frame, textvariable=self.sort, values=['title', 'price', 'rating', 'popularity', 'new arrivals'], state='readonly').pack(anchor='w', pady=8)
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        for text, action in [('Search', self.new_search), ('Attach cover image', self.pick_picture), ('Clear filters', self.clear_filters), ('Previous', lambda: self.paginate(-1)), ('Next', lambda: self.paginate(1))]:
            ttk.Button(actions, text=text, command=self.guard(action)).pack(side='left', padx=(0, 5))
        self.catalog_info = ttk.Label(frame)
        self.catalog_info.pack(anchor='w', pady=8)
        self.book_tree = self.tree(frame, ('Title', 'Author', 'Category', 'Year', 'Price', 'Rating', 'Availability'))
        self.book_tree.bind('<Double-1>', self.guard(lambda e: self.open_selected()))
        self.book_tree.bind('<Return>', self.guard(lambda e: self.open_selected()))
        ttk.Button(frame, text='Open selected book', command=self.guard(self.open_selected)).pack(anchor='e', pady=8)

    def tree(self, frame, columns):
        container = ttk.Frame(frame)
        container.pack(fill='both', expand=True)
        tree = ttk.Treeview(container, columns=columns, show='headings', selectmode='browse')
        for name in columns:
            tree.heading(name, text=name)
            tree.column(name, width=110, minwidth=65)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        return tree

    def new_search(self):
        self.page = 0
        self.search()

    def pick_picture(self):
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg *.webp')], parent=self)
        if path:
            self.picture = path
            self.new_search()

    def clear_filters(self):
        for var in self.filters.values():
            var.set('')
        self.picture = ''
        self.new_search()

    def paginate(self, delta):
        self.page = max(0, self.page + delta)
        self.search()

    def search(self):
        books, count = self.svc.catalog(**{k: v.get() for k, v in self.filters.items()}, sort=self.sort.get(), page=self.page, picture=self.picture)
        if self.page and self.page * 20 >= count:
            self.page = max(0, (count-1)//20)
            return self.search()
        self.book_tree.delete(*self.book_tree.get_children())
        for b in books:
            self.book_tree.insert('', 'end', iid=b['id'], values=(b['title'], b['author'], b['category'], b['year'], self.svc.dollars(b['price']), f"{b['rating']:.1f} ({b['rating_count']})", 'Unavailable' if b['order_list'] == 'no-order' else 'Available'))
        self.catalog_info.configure(text=f'{count} books • Page {self.page+1}' + (' • Perceptual cover search: nearest results' if self.picture else ''))

    def open_selected(self):
        selected = self.book_tree.selection()
        if selected:
            self.detail(selected[0])
# Detail Window
# Ask-the-Book feature contains a spoiler shield
    def detail(self, bid):
        book = self.svc.view(bid)
        window = tk.Toplevel(self)
        window.title(book['title'])
        window.geometry('800x740')
        tabs = ttk.Notebook(window)
        tabs.pack(fill='both', expand=True, padx=12, pady=12)
        info = ttk.Frame(tabs, padding=12)
        tabs.add(info, text='Book & reviews')
        ttk.Label(info, text=book['title'], font=('TkDefaultFont', 20, 'bold'), wraplength=700).pack(anchor='w')
        ttk.Label(info, text=f"{book['author']} • {book['category']} • {book['year']} • {self.svc.dollars(book['price'])}").pack(anchor='w', pady=8)
        if book.get('cover'):
            try:
                from PIL import Image, ImageTk
                with Image.open(self.svc.store.root / book['cover']) as image:
                    image.thumbnail((100, 140))
                    photo = ImageTk.PhotoImage(image)
                label = ttk.Label(info, image=photo)
                label.image = photo
                label.pack(anchor='w')
            except (ImportError, OSError):
                pass
        ttk.Label(info, text=book['description'], wraplength=700).pack(anchor='w', pady=8)
        ttk.Label(info, text=f"Rating: {book['rating']:.1f}/5 • {book['rating_count']} reviews • {book['order_list'] or 'Available'}").pack(anchor='w')
        buy = ttk.Button(info, text='Add to cart', command=self.guard(lambda: self.add_cart(bid)))
        buy.pack(anchor='w', pady=8)
        if book['order_list'] == 'no-order':
            buy.state(['disabled'])
        reviews = tk.Text(info, height=8, wrap='word')
        reviews.pack(fill='both', expand=True)
        for r in book['reviews']:
            reviews.insert('end', f"{r['name']} • {r['stars']}/5 {'• Verified purchase' if r['weight'] == 2 else ''}\n{r['comment']}\n\n")
        reviews.configure(state='disabled')
        stars = tk.StringVar(value='5')
        ttk.Combobox(info, textvariable=stars, values=['1', '2', '3', '4', '5'], state='readonly', width=5).pack(anchor='w', pady=6)
        comment = tk.Text(info, height=3, wrap='word')
        comment.pack(fill='x')
        def post():
            ok = self.svc.review(bid, int(stars.get()), comment.get('1.0', 'end-1c'))
            messagebox.showinfo('Review', 'Review saved.' if ok else 'Review blocked; one warning recorded.', parent=window)
            window.destroy()
            self.refresh()
        ttk.Button(info, text='Post / update review', command=self.guard(post)).pack(anchor='e', pady=6)
        if book['chapters']:
            ask = ttk.Frame(tabs, padding=12)
            tabs.add(ask, text='Ask-the-Book')
            ttk.Label(ask, text='Spoiler Shield • Set the last chapter you have finished.').pack(anchor='w')
            progress = tk.IntVar(value=self.ai.progress(bid))
            tk.Scale(ask, variable=progress, from_=0, to=len(book['chapters']), orient='horizontal', resolution=1).pack(fill='x')
            question = tk.StringVar()
            ttk.Entry(ask, textvariable=question).pack(fill='x', pady=8)
            answer = tk.Text(ask, wrap='word', height=15)
            answer.pack(fill='both', expand=True)
            def send():
                q, n = question.get(), progress.get()
                self.worker(lambda: self.ai.ask_book(bid, n, q), lambda text: self.write(answer, text))
            ttk.Button(ask, text='Ask about completed chapters', command=self.guard(send)).pack(anchor='e', pady=5)
            actions = ttk.Frame(ask)
            actions.pack(fill='x')
            for label, prompt in [('Recap', 'Recap so far'), ("Who's who", 'Describe the characters introduced so far'), ('Quiz me', 'Create 5 questions using only the supplied passages'), ('Explain passage', 'Explain this passage from completed chapters: ')]:
                ttk.Button(actions, text=label, command=lambda p=prompt: question.set(p)).pack(side='left', padx=3)
            ttk.Button(ask, text='Read answer aloud', command=self.guard(lambda: self.read_aloud(answer.get('1.0', 'end')))).pack(anchor='w', pady=5)

    def write(self, widget, text):
        if widget.winfo_exists():
            widget.insert('end', text + '\n\n')
            widget.see('end')

    def read_aloud(self, text):
        binary = shutil.which('espeak-ng') or shutil.which('espeak')
        if not binary:
            raise ValueError('Install espeak-ng to enable offline read aloud on this machine.')
        self.worker(lambda: subprocess.Popen([binary, '--stdin'], stdin=subprocess.PIPE).communicate(text.encode()))

# Cart and Checkout tab
    def add_cart(self, bid):
        self.svc._actor(self.svc.store.snapshot(), {'RC', 'VC'})
        if bid not in self.cart:
            self.cart.append(bid)
        self.render_cart()
        self.status.set('Added to cart.')

    def render_cart(self):
        frame = self.frames['Cart']
        self.clear(frame)
        ttk.Label(frame, text='Your cart', font=('TkDefaultFont', 20, 'bold')).pack(anchor='w')
        lookup = {b['id']: b for b in self.svc.store.snapshot()['books']}
        subtotal = 0
        for bid in self.cart:
            book = lookup[bid]
            subtotal += book['price']
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=6)
            ttk.Label(row, text=f"{book['title']} • {self.svc.dollars(book['price'])}").pack(side='left')
            ttk.Button(row, text='Remove', command=self.guard(lambda b=bid: self.remove_cart(b))).pack(side='right')
        user = self.svc.me()
        total = int((Decimal(subtotal) * Decimal('.9')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if user and user['role'] == 'VC' else subtotal
        ttk.Label(frame, text=f'Subtotal: {self.svc.dollars(subtotal)} • Total: {self.svc.dollars(total)}').pack(anchor='w', pady=12)
        ttk.Label(frame, text='An unaffordable checkout deducts a $1 fine. A negative balance suspends the account.').pack(anchor='w')
        ttk.Button(frame, text='Confirm purchase', command=self.guard(self.checkout)).pack(anchor='w', pady=12)

    def remove_cart(self, bid):
        self.cart.remove(bid)
        self.render_cart()

    def checkout(self):
        result = self.svc.checkout(self.cart)
        if result['ok'] or not self.svc.me():
            self.cart.clear()
        messagebox.showinfo('Checkout', result['message'], parent=self)
        self.refresh()

# Account tab [customer only] - balance, library, ledger
    def render_account(self):
        frame = self.frames['My Account']
        self.clear(frame)
        user = self.svc.me()
        if not user or user['role'] not in ('RC', 'VC'):
            ttk.Label(frame, text='Log in as a customer to manage your balance and library.').pack(anchor='w')
            return
        data = self.svc.account()
        ttk.Label(frame, text=f"{user['name']} • {self.svc.dollars(user['balance'])} • {user['role']}", font=('TkDefaultFont', 20, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=f"Warnings: {user['warnings']} • Books purchased: {user['purchases']} • Spent: {self.svc.dollars(user['spent'])}\nVIP: more than 3 books purchased OR more than $200 spent.").pack(anchor='w', pady=8)
        def deposit():
            value = simpledialog.askstring('Deposit', 'Simulated deposit, $1–$1,000:', parent=self)
            if value:
                self.svc.deposit(value)
                self.refresh()
        ttk.Button(frame, text='Deposit funds', command=self.guard(deposit)).pack(anchor='w')
        ttk.Label(frame, text='My Library', font=('TkDefaultFont', 14, 'bold')).pack(anchor='w', pady=10)
        for book in data['library']:
            ttk.Button(frame, text=book['title'], command=self.guard(lambda bid=book['id']: self.detail(bid))).pack(anchor='w')
        history = self.tree(frame, ('Date', 'Event', 'Amount', 'Balance'))
        for row in reversed(data['ledger']):
            history.insert('', 'end', values=(row['time'][:19], row['kind'], self.svc.dollars(row['delta']), self.svc.dollars(row['balance'])))

    def make_chat(self):
        frame = self.frames['Assistant']
        ttk.Label(frame, text='Ask about the store, books, or your account. Answers show their source.').pack(anchor='w')
        self.chat_output = tk.Text(frame, wrap='word')
        self.chat_output.pack(fill='both', expand=True, pady=8)
        self.chat_question = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.chat_question)
        entry.pack(fill='x')
        entry.bind('<Return>', self.guard(lambda e: self.send_chat()))
        ttk.Button(frame, text='Send', command=self.guard(self.send_chat)).pack(anchor='e', pady=8)

# Incorporated AI chat
    def send_chat(self):
        question = self.chat_question.get()
        self.chat_question.set('')
        self.write(self.chat_output, 'You: ' + question)
        self.worker(lambda: self.ai.chat(question), lambda answer: self.write(self.chat_output, answer))

    def make_admin(self):
        frame = self.frames['SU Console']
        for label, action in [('Add book', self.edit_book), ('Edit selected catalog book', lambda: self.edit_book(True)),
             ('Deactivate selected catalog book', self.deactivate), ('Override selected book list', self.override),
             ('Manage taboo words', self.taboo), ('Accounts / reopen / biometrics', self.accounts),
             ('Reports', self.reports), ('Enroll my administrator face', lambda: self.worker(self.svc.enroll_admin)),
             ('Retrain face model', lambda: self.worker(self.retrain))]:
            ttk.Button(frame, text=label, command=self.guard(action)).pack(anchor='w', pady=4)

    def retrain(self):
        self.svc._actor(self.svc.store.snapshot(), {'SU'})
        self.svc.face.retrain()

    def selected_bid(self):
        selected = self.book_tree.selection()
        if not selected:
            raise ValueError('Select a book in Catalog first.')
        return selected[0]
# SU Console [Admin only] - add/edit books, deactivate, override, taboo words, accounts, reports
    def edit_book(self, edit=False):
        self.svc._actor(self.svc.store.snapshot(), {'SU'})
        bid = self.selected_bid() if edit else None
        book = self.svc._book(self.svc.store.snapshot(), bid) if bid else {}
        keys = ['title', 'author', 'category', 'year', 'price', 'description', 'tags']
        fields = [(k, k.replace('_', ' ').title(), str(book.get(k, '')) if k != 'price' else str(book.get(k, 0)/100)) for k in keys]
        fields += [('cover', 'Cover image path (optional)', ''), ('figures', 'Figure image paths, separated by ;', ''), ('full_text', 'UTF-8 full text path (optional)', '')]
        values = self.form('Edit book' if bid else 'Add book', fields, files={'cover', 'figures', 'full_text'})
        if values:
            values['figures'] = [v.strip() for v in values['figures'].split(';') if v.strip()]
            self.svc.save_book(values, bid)
            self.refresh()

    def deactivate(self):
        bid = self.selected_bid()
        if messagebox.askyesno('Deactivate', 'Remove this book from sale? Order history is retained.', parent=self):
            self.svc.admin_action('deactivate', bid=bid)
            self.refresh()

    def override(self):
        value = simpledialog.askstring('Order list override', 'Enter: auto, normal, to-order, or no-order', parent=self)
        if value is not None:
            self.svc.admin_action('override', bid=self.selected_bid(), value='' if value == 'auto' else value)
            self.refresh()

    def taboo(self):
        self.svc._actor(self.svc.store.snapshot(), {'SU'})
        window = tk.Toplevel(self)
        window.title('Taboo words • one per line')
        text = tk.Text(window, width=50, height=18)
        text.pack(fill='both', expand=True)
        text.insert('1.0', '\n'.join(r['word'] for r in self.svc.store.snapshot()['taboo_words']))
        remask = tk.BooleanVar()
        ttk.Checkbutton(window, text='Re-mask existing comments (no new warnings)', variable=remask).pack()
        def save():
            self.svc.admin_action('taboo', words=text.get('1.0', 'end'), remask=remask.get())
            window.destroy()
        ttk.Button(window, text='Save', command=self.guard(save)).pack(pady=8)

    def accounts(self):
        users = self.svc.admin_users()
        window = tk.Toplevel(self)
        window.title('Customer accounts')
        window.geometry('950x450')
        tree = self.tree(window, ('Username', 'Role', 'Status', 'Balance', 'Warnings', 'Reason'))
        for u in users:
            tree.insert('', 'end', iid=u['id'], values=(u['username'], u['role'], u['status'], self.svc.dollars(u['balance']), u['warnings'], u['suspension_reason']))
        def reopen():
            if tree.selection():
                amount = simpledialog.askstring('Reopen account', 'Deposit amount ($), sufficient to make balance positive:', parent=window)
                if amount:
                    self.svc.admin_action('reopen', uid=tree.selection()[0], amount=amount)
                    window.destroy()
                    self.accounts()
        def delete():
            if tree.selection() and messagebox.askyesno('Delete biometric samples', 'Delete the selected account’s face samples? The customer cannot log in until re-enrolled.', parent=window):
                uid = tree.selection()[0]
                self.worker(lambda: self.svc.admin_action('delete_biometrics', uid=uid))
        def reenroll():
            if tree.selection():
                uid = tree.selection()[0]
                def task():
                    self.svc._actor(self.svc.store.snapshot(), {'SU'})
                    self.svc.face.enroll(uid)
                    with self.svc.store.transaction() as state:
                        self.svc._actor(state, {'SU'})
                        self.svc._user(state, uid)['biometrics'] = True
                self.worker(task)
        ttk.Button(window, text='Deposit & reopen', command=self.guard(reopen)).pack(side='left', padx=8, pady=8)
        ttk.Button(window, text='Delete biometric samples', command=self.guard(delete)).pack(side='left', padx=8)
        ttk.Button(window, text='Re-enroll selected face', command=self.guard(reenroll)).pack(side='left', padx=8)

    def reports(self):
        period = simpledialog.askstring('Report period', 'day, week, month, or all:', initialvalue='all', parent=self)
        if period:
            report = self.svc.report(period)
            window = tk.Toplevel(self)
            window.title('Financial & moderation report • money in cents')
            text = tk.Text(window, wrap='word', width=100, height=32)
            text.pack(fill='both', expand=True)
            text.insert('1.0', json.dumps(report, indent=2))
            text.configure(state='disabled')
            def export():
                path = filedialog.asksaveasfilename(defaultextension='.json', parent=window)
                if path:
                    from pathlib import Path
                    Path(path).write_text(json.dumps(report, indent=2), encoding='utf-8')
            ttk.Button(window, text='Export JSON', command=self.guard(export)).pack(pady=8)
