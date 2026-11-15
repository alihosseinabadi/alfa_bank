"""HTTP behavior is tested without live network dependencies."""
import httpx
from app.data_preparation.url_checks import check_url

def test_timeout_is_temporary_and_retries_are_bounded():
    attempts=[]
    def handler(request):
        attempts.append(request)
        raise httpx.ReadTimeout("timeout",request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=check_url("https://example.org/a",client,retries=1)
    assert result["state"]=="temporary_failure"
    assert result["attempts"]==len(attempts)==2

def test_missing_page_and_head_fallback():
    def handler(request):
        if request.url.path=="/missing":
            return httpx.Response(404)
        return httpx.Response(405 if request.method=="HEAD" else 200)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert check_url("https://example.org/missing",client)["state"]=="unavailable"
        assert check_url("https://example.org/a",client)["state"]=="reachable"

def test_authentication_is_not_a_missing_page():
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(401))) as client:
        result=check_url("https://example.org/a",client)
    assert result["state"]=="reachable" and result["requires_auth_or_blocked_probe"]

def test_invalid_scheme_never_requested():
    def handler(request):
        raise AssertionError("Must not request invalid URL")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert check_url("javascript:alert(1)",client)["state"]=="unavailable"
