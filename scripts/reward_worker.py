"""Run the reward projection loop against the explicitly configured events DB."""
import argparse
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import get_settings
from app.database.connection import events_engine, events_sessions
from app.services.learning_configuration import learning_service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--interval', type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.interval <= 3600:
        parser.error('interval must be between 1 and 3600 seconds')
    engine = events_engine()
    stop = False
    def request_stop(_signum, _frame):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        demo = get_settings().demo_fast_learning
        service = learning_service(events_sessions(engine), demo=demo, database_name=engine.url.database)
        print('TEST SIMULATION: isolated fast learning' if demo else 'Standard delayed reward policy', flush=True)
        while not stop:
            try:
                changed = service.tick()
                if changed:
                    print(f'Updated reward observations: {changed}', flush=True)
            except Exception as exc:
                # Do not print DSNs, personal data or raw database errors.
                print(f'Reward processing failed: {type(exc).__name__}', file=sys.stderr, flush=True)
                if args.once:
                    raise
            if args.once:
                break
            end = time.monotonic() + args.interval
            while not stop and time.monotonic() < end:
                time.sleep(min(.25, max(0, end - time.monotonic())))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
