"""Desktop smoke tests for the BookNest GUI."""
import os
import tempfile
import unittest
from unittest.mock import patch
from booknest.services import BookNest
from booknest.seed import populate


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'Needs a desktop display')
class DesktopSmoke(unittest.TestCase):
    def setUp(self):
        from booknest.ui import App
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.svc = BookNest(self.temp.name)
        populate(self.svc)
        self.svc.setup_admin('test-passphrase-123')
        self.app = App(self.svc)
        self.addCleanup(self.app.destroy)
        self.app.update()

    def test_catalog_home_and_detail_widgets(self):
        self.assertEqual(len(self.app.book_tree.get_children()), 5)
        self.app.detail('book-1')
        self.app.update()
        self.assertEqual(len([c for c in self.app.winfo_children() if c.winfo_class() == 'Toplevel']), 1)
        self.app.filters['query'].set('sherlock')
        self.app.new_search()
        self.assertEqual(len(self.app.book_tree.get_children()), 1)
        self.app.clear_filters()
        self.app.resize_font(1)

    def test_customer_cart_account_and_logout(self):
        class FakeFace:
            def enroll(self, uid):
                pass
        self.svc._face = FakeFace()
        self.svc.register('reader', 'Reader', '100')
        self.app.refresh()
        self.app.add_cart('book-1')
        with patch('booknest.ui.messagebox.showinfo'):
            self.app.checkout()
        self.assertEqual(len(self.svc.account()['library']), 1)
        self.app.detail('book-1')
        self.app.update()
        self.app.logout()
        self.app.update()
        self.assertEqual(self.app.cart, [])
        self.assertEqual(len([c for c in self.app.winfo_children() if c.winfo_class() == 'Toplevel']), 0)

    def test_admin_console_and_report_render(self):
        self.svc.recover_admin('test-passphrase-123')
        self.app.refresh()
        self.app.accounts()
        self.app.taboo()
        with patch('booknest.ui.simpledialog.askstring', return_value='all'):
            self.app.reports()
        self.app.update()
        self.assertEqual(self.app.tabs.tab(self.app.frames['SU Console'], 'state'), 'normal')
