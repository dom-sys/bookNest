import argparse
from pathlib import Path
from .services import BookNest
from .seed import populate


def main():
    parser = argparse.ArgumentParser(description='BookNest local desktop bookstore')
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent.parent / 'data')
    parser.add_argument('--seed', action='store_true', help='Add demo catalog if the catalog is empty')
    parser.add_argument('--check', action='store_true', help='Validate journal and exit without a GUI')
    args = parser.parse_args()
    service = BookNest(args.data_dir)
    if args.seed:
        populate(service)
    if args.check:
        state = service.store.snapshot()
        for user in state['users']:
            replayed = sum(r['delta'] for r in state['ledger'] if r['user_id'] == user['id'])
            if replayed != user['balance']:
                raise SystemExit(f"Ledger mismatch for {user['username']}")
        print(f"Journal OK; {len(state['books'])} books; all balances match the ledger.")
        return
    from .ui import App
    App(service).mainloop()


if __name__ == '__main__':
    main()
