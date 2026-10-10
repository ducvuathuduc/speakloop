import os, socket, sys, threading, time
from pathlib import Path

import pytest

# Never route localhost test traffic through a corporate/sandbox proxy.
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="session")
def server_url(tmp_path_factory):
    os.environ["SPEAKLOOP_DB"] = str(tmp_path_factory.mktemp("db") / "test.db")
    os.environ["SPEAKLOOP_LLM"] = "rules"
    import uvicorn
    from speakloop import server as srv

    port = _free_port()
    config = uvicorn.Config(srv.build_app("127.0.0.1", port), host="127.0.0.1", port=port, log_level="warning")
    s = uvicorn.Server(config)
    t = threading.Thread(target=s.run, daemon=True)
    t.start()
    for _ in range(100):
        if s.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    s.should_exit = True
    t.join(timeout=5)
