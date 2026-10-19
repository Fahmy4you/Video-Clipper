import pytest
from google import genai
from app.schemas import gemini_highlight_config


def test_highlight_schema_reaches_transport_without_sdk_validation_error(monkeypatch):
    class RequestReady(Exception):
        pass
    captured = {}
    with genai.Client(api_key='test-only-no-network') as client:
        def request(method, path, body, *args, **kwargs):
            captured.update(body)
            raise RequestReady()
        monkeypatch.setattr(client._api_client, 'request', request)
        with pytest.raises(RequestReady):
            client.models.generate_content(model='gemini-test', contents='test', config=gemini_highlight_config())
    assert captured['generationConfig']['responseMimeType'] == 'application/json'
    assert 'responseJsonSchema' in captured['generationConfig']
