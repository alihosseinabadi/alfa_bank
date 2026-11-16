"""Manual serialized learner tick/checkpoint; requires explicit events DB URL."""
import argparse
import json
from app.database.connection import events_engine, events_sessions
from app.services.learning_service import LearningService
from app.services.learning_checkpoint import write_checkpoint, load_checkpoint

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['tick','checkpoint','verify'])
    parser.add_argument('--checkpoint', default='artifacts/linucb/checkpoint.json')
    args = parser.parse_args()
    service = LearningService(events_sessions(events_engine()))
    if args.action == 'tick': result = {'changed':service.tick()}
    elif args.action == 'checkpoint': result = {'state_id':write_checkpoint(args.checkpoint, service)}
    else: result = {'state_id':load_checkpoint(args.checkpoint, service).state_id}
    print(json.dumps(result))

if __name__ == '__main__': main()
