import pytest
import pandas as pd
from fastapi.testclient import TestClient
from drift_communities import api

@pytest.fixture(autouse=True)
def isolated_ai_configuration(monkeypatch):
 for name in ('AI_PROVIDER','OPENAI_API_KEY','BEDROCK_MODEL_ID'):
  monkeypatch.delenv(name,raising=False)


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


def test_overview_reports_openai_without_exposing_credentials(monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','test-only-secret')
 monkeypatch.setattr(api,'list_runs',lambda:pd.DataFrame([{'run_id':'synthetic'}]))
 monkeypatch.setattr(api,'community_sizes',lambda run:pd.DataFrame([{'community_id':1,'n_providers':3}]))
 response=TestClient(api.app).get('/api/overview')
 assert response.json()['ai_available'] is True
 assert response.json()['ai_provider']=='openai'
 assert 'test-only-secret' not in response.text


@pytest.mark.parametrize('provider',['openai','bedrock'])
def test_explanation_routes_the_existing_context_to_selected_adapter(monkeypatch,provider):
 from drift_communities import llm_openai,llm_bedrock
 monkeypatch.setenv('AI_PROVIDER',provider)
 monkeypatch.setenv('OPENAI_API_KEY','test-only-secret')
 monkeypatch.setenv('BEDROCK_MODEL_ID','test-only-model')
 context={'provider':{'npi':'0000000001'}}
 seen=[]
 monkeypatch.setattr(api,'build_explain_context',lambda *args:context)
 def explain(ctx):
  seen.append(ctx)
  return {'summary':'synthetic explanation'}
 target=llm_openai if provider=='openai' else llm_bedrock
 monkeypatch.setattr(target,'explain_with_'+provider,explain)
 response=TestClient(api.app).post('/api/providers/0000000001/explanation?run_id=synthetic&cid=1')
 assert response.status_code==200
 assert response.json()['summary']=='synthetic explanation'
 assert seen==[context]


@pytest.mark.parametrize('provider',['none','invalid','bedrock'])
def test_disabled_or_unconfigured_provider_never_reads_evidence(monkeypatch,provider):
 monkeypatch.setenv('AI_PROVIDER',provider)
 monkeypatch.setenv('OPENAI_API_KEY','test-only-secret')
 def unexpected(*args):raise AssertionError('No evidence or model call expected')
 monkeypatch.setattr(api,'build_explain_context',unexpected)
 assert TestClient(api.app).post('/api/providers/1/explanation?run_id=synthetic&cid=1').status_code==503


def test_ai_failure_is_sanitized_and_evidence_endpoint_still_works(monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','test-only-secret')
 monkeypatch.setattr(api,'build_explain_context',lambda *args:{'provider':{'npi':'1'}})
 monkeypatch.setattr(api,'explain',lambda ctx:{'error':'sensitive upstream message'})
 monkeypatch.setattr(api,'evidence_snapshot_metrics',lambda ctx:{'peers_used':1})
 client=TestClient(api.app)
 response=client.post('/api/providers/1/explanation?run_id=synthetic&cid=1')
 assert response.status_code==502
 assert 'sensitive' not in response.text
 assert client.get('/api/providers/1?run_id=synthetic&cid=1').status_code==200


def test_missing_provider_does_not_call_ai(monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','test-only-secret')
 monkeypatch.setattr(api,'build_explain_context',lambda *args:{'error':'not found'})
 def unexpected(*args):raise AssertionError('No model call expected')
 monkeypatch.setattr(api,'explain',unexpected)
 assert TestClient(api.app).post('/api/providers/1/explanation?run_id=synthetic&cid=1').status_code==404
