from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from difflib import SequenceMatcher
from pathlib import Path
import math
import re
import shutil
import uuid
from .config import DEMOTE_WARNINGS, SUSPEND_WARNINGS
from .moderation import filter_comment, normalize
from .security import Session, hash_secret, check_secret
from .storage import Store


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return uuid.uuid4().hex


def tokens(text):
    return re.findall(r'\w+', text.lower())


def similarity(a, b):
    ca, cb = Counter(tokens(a)), Counter(tokens(b))
    dot = sum(v * cb[k] for k, v in ca.items())
    norm = math.sqrt(sum(v*v for v in ca.values()) * sum(v*v for v in cb.values()))
    return dot / norm if norm else 0.0


class BookNest:
    def __init__(self, root):
        self.store = Store(root)
        self.session = Session()
        self._face = None
        self.failures = 0
        self.locked_until = 0

    @staticmethod
    def money(value):
        try:
            number = Decimal(str(value))
            if not number.is_finite() or abs(number) > Decimal('1000000000'):
                raise ValueError('Invalid amount.')
            return int((number * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        except (InvalidOperation, TypeError):
            raise ValueError('Enter a valid dollar amount.') from None

    @staticmethod
    def dollars(cents):
        return f'${cents / 100:,.2f}'

    def _actor(self, s, roles=None):
        uid = self.session.user_id()
        user = next((u for u in s['users'] if u['id'] == uid), None)
        if uid and (not user or user['status'] != 'Active'):
            self.session.logout()
            raise ValueError('Your account is suspended. Please contact the store to reopen it.')
        if roles and (not user or user['role'] not in roles):
            raise ValueError('Your account does not have access to this action.')
        return user

    def me(self):
        return self._actor(self.store.snapshot())

    def _book(self, s, bid):
        book = next((b for b in s['books'] if b['id'] == bid and b['active']), None)
        if not book:
            raise ValueError('Book is unavailable.')
        return book

    def _user(self, s, uid):
        user = next((u for u in s['users'] if u['id'] == uid), None)
        if not user:
            raise ValueError('Account does not exist.')
        return user

    def _ledger(self, s, user, delta, kind, **extra):
        user['balance'] += delta
        s['ledger'].append({'id': identifier(), 'time': now(), 'user_id': user['id'],
                            'kind': kind, 'delta': delta, 'balance': user['balance'], **extra})

    def setup_admin(self, passphrase):
        recovery = hash_secret(passphrase)
        with self.store.transaction() as s:
            if any(u['role'] == 'SU' for u in s['users']):
                raise ValueError('Administrator already exists.')
            s['users'].append({'id': identifier(), 'username': 'admin', 'name': 'Store administrator',
                'role': 'SU', 'status': 'Active', 'balance': 0, 'warnings': 0,
                'purchases': 0, 'spent': 0, 'suspension_reason': '', 'recovery': recovery,
                'biometrics': False, 'created': now()})

    def _check_cooldown(self):
        import time
        if time.monotonic() < self.locked_until:
            raise ValueError('Three failed attempts. Wait 60 seconds or continue as a visitor.')

    def _failed_login(self):
        import time
        self.failures += 1
        if self.failures >= 3:
            self.locked_until = time.monotonic() + 60
            self.failures = 0

    def recover_admin(self, passphrase):
        self._check_cooldown()
        s = self.store.snapshot()
        user = next((u for u in s['users'] if u['role'] == 'SU'), None)
        if not user or not check_secret(passphrase, user['recovery']):
            self._failed_login()
            raise ValueError('Recovery passphrase was not accepted.')
        if user['status'] != 'Active':
            raise ValueError('Administrator account is suspended.')
        self.session.authenticate(user['id'])
        self.failures = 0

    @property
    def face(self):
        if self._face is None:
            from .biometrics import FaceIdentity
            self._face = FaceIdentity(self.store.root)
        return self._face

    def register(self, username, name, opening):
        if self.me():
            raise ValueError('Log out before registering.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,32}', username):
            raise ValueError('Username: 3–32 letters, numbers, underscores or hyphens.')
        if not name.strip():
            raise ValueError('Enter a display name.')
        cents = self.money(opening)
        if not 0 < cents <= 100000:
            raise ValueError('Opening deposit must be above $0 and at most $1,000.')
        if any(u['username'].casefold() == username.casefold() for u in self.store.snapshot()['users']):
            raise ValueError('Username already exists.')
        uid = identifier()
        self.face.enroll(uid)  # Camera samples must succeed before account creation.
        with self.store.transaction() as s:
            user = {'id': uid, 'username': username, 'name': name.strip(), 'role': 'RC',
                'status': 'Active', 'balance': 0, 'warnings': 0, 'purchases': 0, 'spent': 0,
                'suspension_reason': '', 'biometrics': True, 'created': now()}
            s['users'].append(user)
            self._ledger(s, user, cents, 'deposit')
        self.session.authenticate(uid)
        return user

    def enroll_admin(self):
        s = self.store.snapshot()
        user = self._actor(s, {'SU'})
        self.face.enroll(user['id'])
        with self.store.transaction() as s:
            self._user(s, user['id'])['biometrics'] = True

    def login_face(self, confirm):
        self._check_cooldown()
        try:
            uid, distance = self.face.identify()
        except ValueError:
            self._failed_login()
            raise
        s = self.store.snapshot()
        user = self._user(s, uid)
        if not user['biometrics'] or user['status'] != 'Active':
            raise ValueError('Account unavailable or suspended. Contact the store administrator.')
        if not confirm(user['name'], distance):
            self._failed_login()
            raise ValueError('Identity rejected. Please retry.')
        self.session.authenticate(uid)
        self.failures = 0

    def owned(self, s, uid):
        return {bid for order in s['orders'] if order['user_id'] == uid for bid in order['book_ids']}

    def rating(self, s, bid):
        rows = [r for r in s['reviews'] if r['book_id'] == bid]
        weight = sum(r['weight'] for r in rows)
        return (sum(r['stars'] * r['weight'] for r in rows) / weight if weight else 0, len(rows))

    def order_list(self, s, book):
        if book.get('list_override'):
            return book['list_override']
        rating, count = self.rating(s, book['id'])
        return 'no-order' if count > 3 and rating < 2 else 'to-order' if count > 3 and rating > 4 else ''

    def catalog(self, query='', category='', author='', year='', sort='title', page=0, picture=''):
        s = self.store.snapshot()
        self._actor(s)
        books = [b.copy() for b in s['books'] if b['active']]
        if category:
            books = [b for b in books if category.casefold() in b['category'].casefold()]
        if author:
            books = [b for b in books if author.casefold() in b['author'].casefold()]
        if year:
            books = [b for b in books if str(b['year']).startswith(str(year))]
        for b in books:
            b['rating'], b['rating_count'] = self.rating(s, b['id'])
            b['order_list'] = self.order_list(s, b)
            b['popularity'] = 3 * sum(b['id'] in o['book_ids'] for o in s['orders']) + sum(v['book_id'] == b['id'] for v in s['views'])
        if query or picture:
            ranked = []
            if query:
                terms = tokens(query)
                for b in books:
                    text = ' '.join(str(b[k]) for k in ('title', 'author', 'description', 'tags'))
                    bt = tokens(text)
                    b['_score'] = sum(max((SequenceMatcher(None, q, t).ratio() for t in bt), default=0) for q in terms) / max(1, len(terms))
                ranked.append(sorted([b for b in books if b['_score'] >= .55], key=lambda b: -b['_score']))
            if picture:
                from .images import rank_images
                image_order = rank_images(picture, books, self.store.root)
                ranked.append([b for bid, score in image_order for b in books if b['id'] == bid])
            fused = Counter()
            for ranking in ranked:
                for i, b in enumerate(ranking):
                    fused[b['id']] += 1 / (60 + i + 1)
            books = sorted([b for b in books if b['id'] in fused], key=lambda b: -fused[b['id']])
        elif sort == 'new arrivals':
            books.sort(key=lambda b: b['created'], reverse=True)
        else:
            key = sort if sort in ('title', 'price', 'rating', 'popularity') else 'title'
            books.sort(key=lambda b: b[key], reverse=key in ('rating', 'popularity'))
        return books[page * 20:(page + 1) * 20], len(books)

    def recommendations(self):
        s = self.store.snapshot()
        user = self._actor(s)
        uid = user['id'] if user else self.session.visitor_id
        owned = self.owned(s, uid)
        history = [(v['book_id'], 1) for v in s['views'] if v['user_id'] == uid] if user and user['role'] in ('RC', 'VC') else []
        history += [(bid, 3) for bid in owned] if user and user['role'] in ('RC', 'VC') else []
        lookup = {b['id']: b for b in s['books']}
        results = []
        for book in s['books']:
            if not book['active'] or book['id'] in owned or self.order_list(s, book) == 'no-order':
                continue
            if history:
                score = sum(w * (.4 * (lookup[bid]['category'] == book['category']) +
                    .3 * (lookup[bid]['author'] == book['author']) +
                    .3 * similarity(lookup[bid]['description'], book['description']))
                    for bid, w in history if bid in lookup)
                reason = 'Related to your browsing and purchases'
            else:
                score = 3 * sum(book['id'] in o['book_ids'] for o in s['orders']) + sum(v['book_id'] == book['id'] for v in s['views'])
                reason = 'Popular now'
            results.append((score, self.rating(s, book['id'])[0], book['created'], book, reason))
        return [(row[3], row[4]) for row in sorted(results, key=lambda x: x[:3], reverse=True)[:3]]

    def view(self, bid):
        with self.store.transaction() as s:
            user = self._actor(s)
            book = self._book(s, bid)
            s['views'].append({'time': now(), 'user_id': user['id'] if user else self.session.visitor_id, 'book_id': bid})
            result = book.copy()
            result['reviews'] = [r for r in s['reviews'] if r['book_id'] == bid]
            result['rating'], result['rating_count'] = self.rating(s, bid)
            result['order_list'] = self.order_list(s, book)
            return result

    def deposit(self, amount):
        cents = self.money(amount)
        if not 100 <= cents <= 100000:
            raise ValueError('Deposit must be between $1 and $1,000.')
        with self.store.transaction() as s:
            user = self._actor(s, {'RC', 'VC'})
            self._ledger(s, user, cents, 'deposit')

    def checkout(self, book_ids):
        ids = list(dict.fromkeys(book_ids))
        if not ids:
            raise ValueError('Your cart is empty.')
        with self.store.transaction() as s:
            user = self._actor(s, {'RC', 'VC'})
            owned = self.owned(s, user['id'])
            books = [self._book(s, bid) for bid in ids]
            if any(b['id'] in owned or self.order_list(s, b) == 'no-order' for b in books):
                raise ValueError('Cart contains an owned or unavailable book.')
            subtotal = sum(b['price'] for b in books)
            total = int((Decimal(subtotal) * Decimal('.90')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if user['role'] == 'VC' else subtotal
            if total > user['balance']:
                self._ledger(s, user, -100, 'fine')
                if user['balance'] < 0:
                    user.update(status='Suspended', suspension_reason='negative balance')
                    self.session.logout()
                return {'ok': False, 'message': 'Insufficient balance; a $1 fine has been applied.'}
            oid = identifier()
            self._ledger(s, user, -total, 'purchase', order_id=oid, gross=subtotal, discount=subtotal-total)
            s['orders'].append({'id': oid, 'time': now(), 'user_id': user['id'], 'book_ids': ids,
                                'subtotal': subtotal, 'total': total, 'discount': subtotal-total})
            user['purchases'] += len(ids)
            user['spent'] += total
            promoted = user['role'] == 'RC' and user['warnings'] < DEMOTE_WARNINGS and (user['purchases'] > 3 or user['spent'] > 20000)
            if promoted:
                user['role'] = 'VC'
            return {'ok': True, 'message': 'Purchase complete.' + (' Congratulations, you are now a VIP!' if promoted else ''), 'total': total}

    def review(self, bid, stars, comment):
        if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5 or len(comment) > 500:
            raise ValueError('Choose 1–5 stars and a comment of at most 500 characters.')
        with self.store.transaction() as s:
            self._book(s, bid)
            user = self._actor(s)
            uid = user['id'] if user else self.session.visitor_id
            masked, count = filter_comment(comment, [r['word'] for r in s['taboo_words']])
            if count > 3:
                s['moderation_log'].append({'time': now(), 'user_id': uid, 'book_id': bid, 'text': comment, 'matches': count, 'action': 'blocked'})
                if user:
                    user['warnings'] += 1
                    if user['role'] != 'SU':
                        if user['warnings'] >= SUSPEND_WARNINGS:
                            user.update(status='Suspended', suspension_reason='warnings')
                            self.session.logout()
                        elif user['warnings'] >= DEMOTE_WARNINGS:
                            user['role'] = 'RC'
                else:
                    # Visitor strikes are tracked in the moderation log per session.
                    pass
                return False
            existing = next((r for r in s['reviews'] if r['user_id'] == uid and r['book_id'] == bid), None)
            if existing and not user:
                raise ValueError('Visitors may post one review per book per session.')
            row = {'id': existing['id'] if existing else identifier(), 'time': now(), 'user_id': uid,
                   'name': user['name'] if user else 'Visitor', 'book_id': bid, 'stars': stars,
                   'comment': masked, 'weight': 2 if bid in self.owned(s, uid) else 1}
            if existing:
                existing.update(row)
            else:
                s['reviews'].append(row)
            s['moderation_log'].append({'time': now(), 'user_id': uid, 'book_id': bid,
                                        'matches': count, 'action': 'masked' if count else 'accepted'})
            return True

    def account(self):
        s = self.store.snapshot()
        user = self._actor(s, {'RC', 'VC'})
        return {'user': user, 'ledger': [r for r in s['ledger'] if r['user_id'] == user['id']],
                'library': [b for b in s['books'] if b['id'] in self.owned(s, user['id'])]}

    def save_book(self, fields, bid=None):
        self._actor(self.store.snapshot(), {'SU'})
        for key in ('title', 'author', 'category'):
            if not str(fields.get(key, '')).strip():
                raise ValueError(f'{key.title()} is required.')
        cents = self.money(fields.get('price', ''))
        if cents <= 0:
            raise ValueError('Price must be positive.')
        try:
            year = int(fields['year'])
        except (ValueError, KeyError):
            raise ValueError('Enter a valid publication year.') from None
        if not 1 <= year <= 9999:
            raise ValueError('Year must be between 1 and 9999.')
        bookid = bid or identifier()
        cover = self._copy_asset(fields.get('cover', ''), 'covers')
        figures = [self._copy_asset(p, 'figures') for p in fields.get('figures', []) if p]
        chapters = None
        if fields.get('full_text'):
            chapters = self.parse_chapters(Path(fields['full_text']).read_text(encoding='utf-8-sig'))
        with self.store.transaction() as s:
            self._actor(s, {'SU'})
            book = self._book(s, bid) if bid else {'id': bookid, 'created': now(), 'chapters': [], 'cover': '', 'figures': [], 'active': True, 'list_override': ''}
            book.update({k: str(fields.get(k, '')).strip() for k in ('title', 'author', 'category', 'description', 'tags')})
            book.update(price=cents, year=year)
            if cover:
                book['cover'] = cover
            if figures:
                book['figures'] = figures
            if chapters is not None:
                book['chapters'] = chapters
            if not bid:
                s['books'].append(book)
        return bookid

    def _copy_asset(self, source, folder):
        if not source:
            return ''
        from PIL import Image
        path = Path(source)
        with Image.open(path) as image:
            image.verify()
        dest = self.store.root / folder / (identifier() + path.suffix.lower())
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        return str(dest.relative_to(self.store.root))

    @staticmethod
    def parse_chapters(text):
        # Anchored headings avoid accidentally splitting ordinary narrative.
        pieces = re.split(r'(?im)^\s*chapter\s+(?:[0-9]+|[ivxlcdm]+)\b[^\n]*\n', text)
        if len(pieces) > 1:
            pieces = pieces[1:]  # Drop front matter rather than expose it as chapter 1.
        return [{'number': i + 1, 'paragraphs': [p.strip() for p in re.split(r'\n\s*\n', chunk) if p.strip()]}
                for i, chunk in enumerate(pieces) if chunk.strip()]

    def admin_action(self, action, **kwargs):
        with self.store.transaction() as s:
            self._actor(s, {'SU'})
            if action == 'taboo':
                words = {normalize(w.strip()) for w in kwargs['words'].splitlines() if w.strip()}
                s['taboo_words'] = [{'word': w} for w in sorted(words)]
                if kwargs.get('remask'):
                    for r in s['reviews']:
                        r['comment'] = filter_comment(r['comment'], words)[0]
            elif action == 'reopen':
                user = self._user(s, kwargs['uid'])
                if user['status'] != 'Suspended' or user['role'] == 'SU':
                    raise ValueError('Select a suspended customer.')
                cents = self.money(kwargs['amount'])
                if cents <= 0 or user['balance'] + cents <= 0:
                    raise ValueError('Deposit must make the balance positive. Minimum: ' + self.dollars(max(1, 1-user['balance'])))
                self._ledger(s, user, cents, 'deposit')
                if user['suspension_reason'] == 'warnings':
                    user['warnings'] = 0
                user.update(status='Active', role='RC', suspension_reason='')
            elif action == 'deactivate':
                self._book(s, kwargs['bid'])['active'] = False
            elif action == 'override':
                if kwargs['value'] not in ('', 'normal', 'to-order', 'no-order'):
                    raise ValueError('Invalid list override.')
                self._book(s, kwargs['bid'])['list_override'] = kwargs['value']
            elif action == 'delete_biometrics':
                user = self._user(s, kwargs['uid'])
                self.face.delete(user['id'])
                user['biometrics'] = False
            else:
                raise ValueError('Unknown administrator action.')

    def report(self, period='all'):
        s = self.store.snapshot()
        self._actor(s, {'SU'})
        if period not in ('all', 'day', 'week', 'month'):
            raise ValueError('Choose day, week, month or all.')
        cutoff = datetime.now(timezone.utc) - timedelta(days={'day': 1, 'week': 7, 'month': 30}.get(period, 365000))
        ledger = [r for r in s['ledger'] if datetime.fromisoformat(r['time']) >= cutoff]
        orders = [o for o in s['orders'] if datetime.fromisoformat(o['time']) >= cutoff]
        sales = sum(o['total'] for o in orders)
        fines = -sum(r['delta'] for r in ledger if r['kind'] == 'fine')
        report = {'period': period, 'deposits': sum(r['delta'] for r in ledger if r['kind'] == 'deposit'),
                  'gross_sales': sum(o['subtotal'] for o in orders), 'VIP_discounts': sum(o['discount'] for o in orders),
                  'fines': fines, 'net_revenue': sales + fines, 'orders': len(orders),
                  'average_order_value': int((Decimal(sales) / Decimal(len(orders))).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if orders else 0,
                  'top_books': Counter(b for o in orders for b in o['book_ids']).most_common(5),
                  'top_customers': Counter(o['user_id'] for o in orders).most_common(5),
                  'order_lists': [{'title': b['title'], 'list': self.order_list(s, b),
                                   'rating': self.rating(s, b['id'])} for b in s['books'] if b['active'] and self.order_list(s, b) in ('to-order', 'no-order')],
                  'moderation': [r for r in s['moderation_log'] if datetime.fromisoformat(r['time']) >= cutoff]}
        return report

    def admin_users(self):
        s = self.store.snapshot()
        self._actor(s, {'SU'})
        return [{k: v for k, v in u.items() if k != 'recovery'} for u in s['users']]
