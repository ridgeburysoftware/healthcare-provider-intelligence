import pandas as pd
from provider_graph.similarity import compute_similarity_and_communities

def test_actual_faiss_builds_similarity_edges_and_communities():
 vectors=pd.DataFrame([[1.0,.9],[1.0,.85],[.01,1.0],[.02,1.0]],index=['0000000001','0000000002','0000000003','0000000004'])
 result=compute_similarity_and_communities(vectors,list(vectors.index),top_k=2,sim_threshold=.8,top_peers=2,random_state=42,use_faiss=True)
 assert len(result.partition)==4
 assert len(result.provider_rows)==4
 assert result.edges
 assert all(a!=b for a,b,score in result.edges)
 assert all(score>=.8 for a,b,score in result.edges)
