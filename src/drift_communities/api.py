"""Local review API: the same Neo4j queries and evidence as the original UI."""
from pathlib import Path
import json
import math
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from .queries import list_runs, community_sizes, providers_in_community, bounded_edges
from .graph_viz import layout_with_centroid, drift_band
from .explain_context import build_explain_context, evidence_snapshot_metrics

app = FastAPI(title='Provider Intelligence', docs_url=None, redoc_url=None)

def records(frame):
    return json.loads(frame.to_json(orient='records'))

@app.exception_handler(ServiceUnavailable)
@app.exception_handler(Neo4jError)
async def database_error(request, exc):
    return Response('{"detail":"The analysis database is unavailable. Check the local Neo4j container and connection settings."}',status_code=503,media_type='application/json')

@app.get('/api/overview')
def overview():
    runs = records(list_runs())
    if not runs: raise HTTPException(503,'No analysis runs were found in the database.')
    run = str(runs[0]['run_id'])
    groups = records(community_sizes(run))
    return {'run_id':run,'runs':runs,'groups':groups,'provider_count':sum(g['n_providers'] for g in groups),'source':'Preserved CMS-derived provider analysis','ai_available':bool(os.getenv('BEDROCK_MODEL_ID'))}

@app.get('/api/groups/{cid}')
def group(cid:int,run_id:str,min_sim:float=Query(.25,ge=0,le=.9),top20:bool=False):
    members = providers_in_community(run_id,cid)
    if members.empty: raise HTTPException(404,'Peer group not found.')
    shown = members.head(20 if top20 else 120).copy()
    edges = bounded_edges(run_id,shown.npi.tolist(),450 if top20 else 1200,min_sim)
    pos = layout_with_centroid(shown.npi.tolist(),edges,f'centroid:{run_id}:{cid}')
    xs=[p[0] for key,p in pos.items() if not key.startswith('centroid:')]
    ys=[p[1] for key,p in pos.items() if not key.startswith('centroid:')]
    spanx=max(max(xs)-min(xs),.001); spany=max(max(ys)-min(ys),.001)
    nodes=[]
    for row in records(shown):
        x,y=pos[row['npi']]
        row.update(x=60+(x-min(xs))/spanx*680,y=45+(y-min(ys))/spany*320,band=drift_band(row['drift_score']))
        nodes.append(row)
    bands={band:int(members.drift_score.map(drift_band).eq(band).sum()) for band in ['GREEN','YELLOW','RED']}
    return {'community_id':cid,'members':records(members),'nodes':nodes,'edges':records(edges),'bands':bands,'mean_drift':float(members.drift_score.mean()),'shown':len(nodes),'min_similarity':min_sim}

@app.get('/api/providers/{npi}')
def provider(npi:str,run_id:str,cid:int):
    ctx=build_explain_context(run_id,cid,npi,5,10)
    if 'error' in ctx: raise HTTPException(404,'Provider not found in this peer group.')
    return {'context':ctx,'metrics':evidence_snapshot_metrics(ctx)}

@app.post('/api/providers/{npi}/explanation')
def explanation(npi:str,run_id:str,cid:int):
    if not os.getenv('BEDROCK_MODEL_ID'): raise HTTPException(503,'AI explanation is not configured. Evidence remains available without an AI provider.')
    ctx=build_explain_context(run_id,cid,npi,5,10)
    if 'error' in ctx: raise HTTPException(404,'Provider not found in this peer group.')
    from .llm_bedrock import explain_with_bedrock
    result=explain_with_bedrock(ctx)
    if 'error' in result: raise HTTPException(502,'The AI provider could not generate an explanation. Review the evidence directly or check the local provider configuration.')
    return result

dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/')
    def index(): return FileResponse(dist/'index.html')
