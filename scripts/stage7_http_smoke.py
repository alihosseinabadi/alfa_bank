"""Smoke test against real local catalog and isolated test event database."""
import os
from uuid import uuid4
from sqlalchemy.engine import make_url

url = os.environ.get('ALFA_EVENTS_DATABASE_URL', '')
if not url or make_url(url).database != 'alfa_events_test':
    raise SystemExit('ALFA_EVENTS_DATABASE_URL must name the isolated alfa_events_test database')
if os.environ.get('ALFA_DEMO_FAST_LEARNING', '').lower() != 'true':
    raise SystemExit('ALFA_DEMO_FAST_LEARNING=true is required')
from fastapi.testclient import TestClient
from app.main import create_app

with TestClient(create_app()) as client:
    sess=client.post('/api/v1/session'); assert sess.status_code==200, sess.text
    h={'X-CSRF-Token':sess.json()['csrf_token']}
    def req(task, **kw):
        body={'request_key':str(uuid4()),'task':task,**kw}
        r=client.post('/api/v1/recommendations',headers=h,json=body)
        assert r.status_code==200, r.text
        x=r.json(); print('recommendation:', task, x['status'], 'cards',len(x['items']), 'links', sorted({i['link_status'] for i in x['items']}))
        return body,x
    body,x=req('Как предпринимателю разобраться с НДС?',constraints={'formats':['article']})
    assert x['items'] and all(i['format']=='article' for i in x['items'])
    assert client.post('/api/v1/recommendations',headers=h,json=body).json()==x
    r=client.post('/api/v1/recommendations',headers=h,json={**body,'task':'Как привлечь клиентов?'})
    assert r.status_code==409
    _,y=req('Как привлечь клиентов в интернет магазин?')
    _,z=req('Квантовая гравитация чёрных дыр')
    assert z['status']=='needs_clarification' and not z['items']
    _,empty=req('Как разобраться с НДС?',constraints={'formats':['podcast']})
    print('restricted format:',empty['status'])
    card=x['items'][0]; vis={'event_key':str(uuid4()),'item_id':card['item_id'],'material_key':card['material_key'],'visible_ms':1200,'visible_fraction':0.8}
    a=client.post('/api/v1/events/visibility',headers=h,json=vis); assert a.status_code==200,a.text
    assert client.post('/api/v1/events/visibility',headers=h,json=vis).json()['id']==a.json()['id']
    click={'event_key':str(uuid4()),'item_id':card['item_id'],'material_key':card['material_key'],'impression_id':a.json()['id'],'kind':'click'}
    c=client.post('/api/v1/events/action',headers=h,json=click); assert c.status_code==200,c.text
    c2=client.post('/api/v1/events/action',headers=h,json=click); assert c2.json()['id']==c.json()['id'] and c2.json()['replayed']
    opened=client.post('/api/v1/events/action',headers=h,json={**click,'event_key':str(uuid4()),'kind':'material_open'}); assert opened.status_code==503
    bad=client.post('/api/v1/recommendations',headers=h,json={'request_key':'bad','task':''}); assert bad.status_code==422
    print('PASS: replay, changed payload 409, visibility, click replay, open 503, invalid request 422')
