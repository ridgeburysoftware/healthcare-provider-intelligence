# tests/test_neo.py
from provider_graph.neo import neo_write, clear_run_relationships

class FakeSession:
    def __init__(self):
        self.calls = []
    def run(self, cypher, **kwargs):
        self.calls.append((cypher.strip(), kwargs))
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False

class FakeDriver:
    def __init__(self):
        self.session_obj = FakeSession()
    def session(self, database=None):
        return self.session_obj

def test_neo_write_batches():
    driver = FakeDriver()
    rows = [{"x": i} for i in range(5)]
    neo_write(driver, "neo4j", "UNWIND $rows AS r RETURN r", rows, batch_size=2)

    # Expect 3 calls: 2+2+1
    assert len(driver.session_obj.calls) == 3
    assert len(driver.session_obj.calls[0][1]["rows"]) == 2
    assert len(driver.session_obj.calls[2][1]["rows"]) == 1

def test_clear_run_relationships_executes_two_deletes():
    driver = FakeDriver()
    clear_run_relationships(driver, "neo4j", run_id="RUN_X")
    assert len(driver.session_obj.calls) == 2
    assert driver.session_obj.calls[0][1]["run_id"] == "RUN_X"
