import copy
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError
from drift_communities import llm_openai as llm


@pytest.fixture
def context():
 return {'provider':{'npi':'0000000001','drift_score':.7,'band':'RED'},
         'peers':[{'peer_npi':'0000000002','sim':.8}],
         'hcpcs':[{'id':'H1','label':'Synthetic service','allowed':120.,'peer_allowed_avg':100.,'delta_allowed':20.}],
         'drugs':[{'id':'D1','label':'Synthetic drug','spend':10.,'peer_spend_avg':100.,'delta_spend':-90.}],
         'unrelated_private_field':'must not be sent'}


@pytest.fixture
def model_output():
 return {'summary':'Synthetic evidence summary.',
         'key_drivers':[{'candidate_index':0,'why_it_matters':'Recorded spending is lower than peers.'}],
         'peer_interpretation':'One comparison peer.',
         'caveats':['Differences do not establish fraud.']}


@pytest.fixture
def fake_openai(monkeypatch,model_output):
 monkeypatch.setenv('OPENAI_API_KEY','test-only-secret')
 monkeypatch.delenv('OPENAI_MODEL',raising=False)
 calls=[]
 state={'text':json.dumps(model_output),'status':'completed','failure':None}
 class Client:
  def __init__(self,**kwargs):
   calls.append(('client',kwargs))
   self.responses=self
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def create(self,**kwargs):
   calls.append(('request',kwargs))
   if state['failure']:raise state['failure']
   return SimpleNamespace(output_text=state['text'],status=state['status'])
 monkeypatch.setattr(llm,'OpenAI',Client)
 return calls,state


def test_responses_request_is_bounded_and_driver_values_come_from_evidence(context,fake_openai,monkeypatch):
 calls,state=fake_openai
 monkeypatch.setenv('OPENAI_MODEL','configured-model')
 original=copy.deepcopy(context)
 out=llm.explain_with_openai(context)
 assert out['key_drivers'][0]['id']=='D1'
 assert out['key_drivers'][0]['evidence']=={'provider_value':10.,'peer_avg_value':100.,'delta':-90.}
 assert out['peer_context']['peers_used']==['0000000002']
 config=calls[0][1];request=calls[1][1]
 assert config['timeout']==30. and config['max_retries']==0
 assert request['store'] is False and request['model']=='configured-model'
 assert request['max_output_tokens']==1600
 assert request['text']['format']['strict'] is True
 assert 'must not be sent' not in request['input']
 assert 'test-only-secret' not in json.dumps(request)
 assert context==original


def test_missing_key_never_constructs_client(context,fake_openai,monkeypatch):
 monkeypatch.delenv('OPENAI_API_KEY',raising=False)
 assert 'error' in llm.explain_with_openai(context)
 assert fake_openai[0]==[]


@pytest.mark.parametrize('missing',['peers','hcpcs_and_drugs'])
def test_missing_comparison_evidence_does_not_call_model(context,fake_openai,missing):
 if missing=='peers':context['peers']=[]
 else:context['hcpcs']=[];context['drugs']=[]
 out=llm.explain_with_openai(context)
 assert out['key_drivers']==[] and 'insufficient' in out['summary']
 assert fake_openai[0]==[]


@pytest.mark.parametrize('indexes',[[10],[-1],[0,0]])
def test_rejects_unknown_or_duplicate_evidence_references(context,fake_openai,model_output,indexes):
 model_output['key_drivers']=[{'candidate_index':i,'why_it_matters':'Test'} for i in indexes]
 fake_openai[1]['text']=json.dumps(model_output)
 assert 'error' in llm.explain_with_openai(context)


@pytest.mark.parametrize('text,status',[('not-json','completed'),('{}','completed'),('','completed'),('{}','incomplete')])
def test_incomplete_refused_or_invalid_outputs_are_safe(context,fake_openai,text,status):
 fake_openai[1].update(text=text,status=status)
 out=llm.explain_with_openai(context)
 assert 'error' in out and 'raw' not in out


def test_timeout_is_sanitized(context,fake_openai):
 fake_openai[1]['failure']=APITimeoutError(request=httpx.Request('POST','https://api.openai.com/v1/responses'))
 assert 'error' in llm.explain_with_openai(context)
 assert len([c for c in fake_openai[0] if c[0]=='request'])==1


def test_nonfinite_evidence_is_not_sent(context,fake_openai):
 context['hcpcs'][0]['allowed']=float('nan')
 llm.explain_with_openai(context)
 packet=json.loads(fake_openai[0][1][1]['input'])
 assert [c['id'] for c in packet['driver_candidates']]==['D1']
