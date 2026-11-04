import pandas as pd
from fastapi.testclient import TestClient
from drift_communities import api

def test_overview_uses_query_results_without_a_real_database(monkeypatch):
 monkeypatch.setattr(api,'list_runs',lambda:pd.DataFrame([{'run_id':'synthetic-test-run'}]))
 monkeypatch.setattr(api,'community_sizes',lambda run:pd.DataFrame([{'community_id':1,'n_providers':3}]))
 monkeypatch.delenv('BEDROCK_MODEL_ID',raising=False)
 response=TestClient(api.app).get('/api/overview')
 assert response.status_code==200
 assert response.json()['provider_count']==3
 assert response.json()['run_id']=='synthetic-test-run'
 assert response.json()['ai_available'] is False

def test_empty_graph_reports_missing_analysis_honestly(monkeypatch):
 monkeypatch.setattr(api,'list_runs',lambda:pd.DataFrame())
 response=TestClient(api.app).get('/api/overview')
 assert response.status_code==503
 assert 'No analysis runs' in response.json()['detail']

def test_explanations_do_not_call_a_provider_without_configuration(monkeypatch):
 monkeypatch.delenv('BEDROCK_MODEL_ID',raising=False)
 def unexpected(*args,**kwargs):raise AssertionError('Evidence/provider work must not start')
 monkeypatch.setattr(api,'build_explain_context',unexpected)
 response=TestClient(api.app).post('/api/providers/0000000001/explanation?run_id=synthetic&cid=1')
 assert response.status_code==503
 assert 'not configured' in response.json()['detail']
