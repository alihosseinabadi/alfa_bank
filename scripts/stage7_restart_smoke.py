"""Isolated test of reward replay and a full backend process restart."""
import os
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = os.environ.get('ALFA_EVENTS_DATABASE_URL', '')
if not url or make_url(url).database != 'alfa_events_test':
    raise SystemExit('ALFA_EVENTS_DATABASE_URL must name the isolated alfa_events_test database')
if os.environ.get('ALFA_DEMO_FAST_LEARNING', '').lower() != 'true':
    raise SystemExit('ALFA_DEMO_FAST_LEARNING=true is required')

with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
base = f'http://127.0.0.1:{port}'
env = dict(os.environ, PYTHONPATH='backend')
process = None

def start():
    p = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(180):
        if p.poll() is not None:
            raise RuntimeError('backend exited while starting')
        try:
            if httpx.get(base + '/docs', timeout=1).status_code == 200:
                return p
        except httpx.TransportError:
            pass
        time.sleep(.5)
    p.terminate(); p.wait(timeout=10)
    raise TimeoutError('backend did not start')

def stop(p):
    p.terminate()
    try:
        p.wait(timeout=15)
    except subprocess.TimeoutExpired:
        p.kill(); p.wait()

def replay():
    code = "from app.database.connection import events_engine,events_sessions; from app.services.learning_configuration import learning_service; e=events_engine(); print(learning_service(events_sessions(e),demo=True,database_name=e.url.database).replay().state_id); e.dispose()"
    return subprocess.check_output([sys.executable, '-c', code], env=env, text=True).strip()

try:
    process = start()
    with httpx.Client(base_url=base, timeout=30) as client:
        session = client.post('/api/v1/session'); session.raise_for_status()
        headers = {'X-CSRF-Token': session.json()['csrf_token']}
        body = {'request_key': str(uuid4()), 'task': 'Как предпринимателю разобраться с НДС?'}
        response = client.post('/api/v1/recommendations', headers=headers, json=body); response.raise_for_status()
        original = response.json(); item = original['items'][0]
        vis = {'event_key': str(uuid4()), 'item_id': item['item_id'], 'material_key': item['material_key'], 'visible_ms': 1200, 'visible_fraction': .8}
        ack = client.post('/api/v1/events/visibility', headers=headers, json=vis); ack.raise_for_status()
        click = {'event_key': str(uuid4()), 'item_id': item['item_id'], 'material_key': item['material_key'], 'impression_id': ack.json()['id'], 'kind': 'click'}
        action = client.post('/api/v1/events/action', headers=headers, json=click); action.raise_for_status()
        before = replay(); time.sleep(3)
        worker = subprocess.check_output([sys.executable, 'scripts/reward_worker.py', '--once'], env=env, text=True)
        after = replay(); assert before != after, 'model state did not change'
        engine = create_engine(url)
        with engine.connect() as db:
            observation = db.execute(text('SELECT reward FROM reward_observations WHERE impression_id = :impression_id AND model_key = :model_key'), {'impression_id': ack.json()['id'], 'model_key': 'demo-fast-linucb-v1'}).scalar_one()
        engine.dispose()
        assert float(observation) == .1, 'expected simulated click reward is missing'
        stop(process); process = None
        process = start()
        repeated = client.post('/api/v1/recommendations', headers=headers, json=body); repeated.raise_for_status()
        assert repeated.json() == original, 'saved response changed after restart'
        assert replay() == after, 'model state changed after restart'
        fresh = client.post('/api/v1/recommendations', headers=headers, json={**body, 'request_key': str(uuid4())}); fresh.raise_for_status()
        assert fresh.json().get('message') != 'Временно использовано базовое ранжирование.', 'model unavailable after restart'
        print(worker.strip())
        print('PASS: model updated, state restored in fresh process, receipt replayed after backend restart, fresh request served')
finally:
    if process is not None:
        stop(process)
