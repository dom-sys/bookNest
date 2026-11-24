import hashlib
import hmac
import secrets
import time
from .config import IDLE_SECONDS


def hash_secret(secret):
    if len(secret) < 12:
        raise ValueError('Use a recovery passphrase of at least 12 characters.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', secret.encode(), bytes.fromhex(salt), 600_000).hex()
    return {'salt': salt, 'digest': digest}


def check_secret(secret, record):
    digest = hashlib.pbkdf2_hmac('sha256', secret.encode(), bytes.fromhex(record['salt']), 600_000).hex()
    return hmac.compare_digest(digest, record['digest'])


class Session:
    """Internal service session. GUI never chooses an authenticated role."""
    def __init__(self):
        self.visitor_id = 'visitor-' + secrets.token_hex(12)
        self._user_id = None
        self.touched = time.monotonic()

    def user_id(self):
        if time.monotonic() - self.touched > IDLE_SECONDS:
            self.logout()
        self.touched = time.monotonic()
        return self._user_id

    def authenticate(self, user_id):
        self._user_id = user_id
        self.touched = time.monotonic()

    def logout(self):
        self._user_id = None
        self.touched = time.monotonic()
