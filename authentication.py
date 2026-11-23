
from datetime import datetime, timezone
import re
import uuid
from .security import hash_secret, check_secret


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return uuid.uuid4().hex


class AuthenticationMixin:
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


    def _user(self, s, uid):
        user = next((u for u in s['users'] if u['id'] == uid), None)
        if not user:
            raise ValueError('Account does not exist.')
        return user


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


    def admin_users(self):
        s = self.store.snapshot()
        self._actor(s, {'SU'})
        return [{k: v for k, v in u.items() if k != 'recovery'} for u in s['users']]

