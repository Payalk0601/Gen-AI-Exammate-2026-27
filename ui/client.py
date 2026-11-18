"""Calls to the KachraCheck API. Every failure becomes an ApiError with a message a user can act on."""
import requests

TIMEOUT = (5, 90)


class ApiError(RuntimeError):
    pass


def _call(method: str, url: str, **kwargs):
    try:
        resp = requests.request(method, url, timeout=kwargs.pop("timeout", TIMEOUT), **kwargs)
    except requests.exceptions.ConnectionError:
        raise ApiError(f"Cannot reach the API at {url.split('/', 3)[0]}//{url.split('/', 3)[2]}. Start it with: uvicorn app.main:app")
    except requests.exceptions.Timeout:
        raise ApiError("The API took too long to answer. Try again, or lower k.")
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ApiError(f"{resp.status_code}: {detail}")
    try:
        return resp.json()
    except ValueError:
        raise ApiError("The API sent a reply that is not JSON.")


def health(api: str) -> dict:
    return _call("GET", f"{api}/health", timeout=(2, 4))


def ask(api: str, question: str, k: int = 4) -> dict:
    return _call("POST", f"{api}/ask", json={"question": question, "k": k})


def agent(api: str, message: str, thread_id: str = None) -> dict:
    return _call("POST", f"{api}/agent", json={"message": message, "thread_id": thread_id})


def approve(api: str, thread_id: str, approved: bool) -> dict:
    return _call("POST", f"{api}/agent", json={"thread_id": thread_id, "approve": approved})
