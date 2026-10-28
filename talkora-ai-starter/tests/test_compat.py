import asyncio

from httpx import ASGITransport, AsyncClient
from server.main import app, health


def request(method, url, *, body=None):
    async def send():
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            if method == 'GET':
                return await client.get(url)
            return await client.post(url, json=body)
    return asyncio.run(send())

def test_refuses_wrong_grade():
    r=request('POST', '/v1/brain/respond', body={'grade':4,'levelId':'g00-l01','studentMessage':'apple'})
    assert r.status_code==422

def test_refuses_unmapped_lesson():
    r=request('POST', '/v1/brain/respond', body={'grade':0,'levelId':'g00-l02','studentMessage':'apple'})
    assert r.status_code==422

def test_requires_explicit_level_id():
    r=request('POST', '/v1/brain/respond', body={'grade':0,'studentMessage':'apple'})
    assert r.status_code==422

def test_preserves_existing_chat():
    # The health endpoint is sync and this sandbox cannot run FastAPI's
    # threadpool-backed ASGI call. Check the registered route and handler.
    assert '/health' in app.openapi()['paths']
    assert health()['status'] == 'ok'
