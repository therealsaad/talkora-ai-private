from fastapi.testclient import TestClient
from server.main import app

client=TestClient(app)

def test_refuses_wrong_grade():
    r=client.post('/v1/brain/respond',json={'grade':4,'levelId':'g00-l01','studentMessage':'apple'})
    assert r.status_code==422

def test_refuses_unmapped_lesson():
    r=client.post('/v1/brain/respond',json={'grade':0,'levelId':'g00-l02','studentMessage':'apple'})
    assert r.status_code==422

def test_requires_explicit_level_id():
    r=client.post('/v1/brain/respond',json={'grade':0,'studentMessage':'apple'})
    assert r.status_code==422

def test_preserves_existing_chat():
    r=client.get('/health')
    assert r.status_code==200
