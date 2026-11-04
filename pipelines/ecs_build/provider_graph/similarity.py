# provider_graph/similarity.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
import networkx as nx
import community as community_louvain

@dataclass(frozen=True)
class SimilarityResult:
    edges: List[Tuple[int, int, float]]                 # directed pairs (i,j,sim)
    provider_rows: List[Tuple[str, int, float, str]]    # (npi,cid,drift_score,top_peers_str)
    partition: Dict[int, int]                           # node_id -> community_id

def _l2_normalize_rows(X: np.ndarray) -> np.ndarray:
    #computes the norm across columns for each row (axis=1 means educe across the feature dimension )
    norms = np.linalg.norm(X, axis=1, keepdims=True) #keeps it as a 2D column vector shape
    #avoids divide by zero errors
    norms[norms == 0.0] = 1.0 

    #example:
    #original matrix:\ whith 3 vectors each with 2 dimensions
    # [3.0, 4.0],
    # [0.0, 0.0],
    # [1.0, 2.0],

    #step 2, compute the L2 norm (length) for each vector. norm = square root of x squared + y squared
    #[3, 4] = 5
    #[0, 0] = 0 (but we set to 1 to avoid divide by zero)
    #[1, 2] = sqrt(1 + 4) = sqrt(5) ~ 2.236

    # Step 3 Divide each row by the norm
    # [3.0, 4.0] / 5 = [0.6, 0.8]
    #sqrt(.36 + .64) = 1.0 (unit vector)
    return X / norms

def _knn_cosine_numpy(X: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns similarity scores for top K neighbors (sims) and indexes of those neighbors(idxs).
    i.e Provider A -> top K most similar providers
        Provider B -> top K most similar providers
    """
    #The data is structured as a 2D matrix (rows, features). Each row is a vector of provider data.
    #We first normalize the rows using linalg.norm which converts the vectors to unit length (euclidian length since we only care about direction, not magnitude)
    #After normalization every row has length 1 and now we can compute cosine similarity.

    Xn = _l2_normalize_rows(X.astype(np.float32, copy=False)) #float32 is what FAISS expects
    #after normalization every row has length 1. The cosine similarity between two unit vectors is just their dot product. 
    # So we can compute the cosine similarity matrix S by multiplying Xn with its transpose. 
    # S[i,j] will give us the cosine similarity between row i and row j.
    #example: if Xn = (n × d) then Xn.T is (d × n) and the result S is (n × n) where S[i,j] is the cosine similarity between row i and row j of Xn.
    
    #S = X @ X.T   → O(n²)
    #memory        → O(n²)
    S = Xn @ Xn.T  # cosine
    # Now we want to find the top K neighbors for each row based on the similarity scores in S. 
    # We use argsort to get the indices of the sorted similarities.
    idxs = np.argsort(-S, axis=1)[:, :k] #axis=1 means sort each row independently. So for every provider: sort all other providers by similarity.
    #this extracts the actual similarity numbers corresponding to the indices of the top K neighbors. np.take_along_axis allows us to index into S using the idxs we just computed.
    sims = np.take_along_axis(S, idxs, axis=1)
    return sims.astype(np.float32), idxs.astype(np.int64)

def compute_similarity_and_communities(
    V: pd.DataFrame, #provider feature matrix (rows = providers, columns = features)
    npis: List[str], # provider identifiers
    #KNN / threshold params
    top_k: int, #how many nearest neighbors to retrieve per provider
    sim_threshold: float, #minimum cosine similarity to accept an edge into the graph
    top_peers: int, #Display for the "top peers" text field
    random_state: int, #makes Louvain reproducible. (Same graph = same partition)
    use_faiss: bool = True, #disable for unit tests
) -> SimilarityResult:
    #SimularityResult constains the following:
    #edges: (i, j, sim). In Neo4j these are SIMILAR_TO relationships
    #provider_rows: (npi, cid, drift_score, top_peers_str) per provider
    #partition: node_id -> community_id mapping. community_id is the Louvain clustering assignment

    #converts to a matrix format expected by FAISS
    X = np.ascontiguousarray(V.values, dtype=np.float32) #ensures memory is contiguous for FAISS
    # X is (n_providers, n_features)
    if X.size == 0:
        return SimilarityResult(edges=[], provider_rows=[], partition={})

    #Compute top-K nearest neighbors based on cosine similarity. 
    # We use FAISS for the real dataset and numpy for tests
    if use_faiss:
        import faiss
        #Normalizes each row to unit length so that the inner product in FAISS corresponds to cosine similarity.
        faiss.normalize_L2(X)
        n, d = X.shape
        #FAISS IndexFlatIP is an index that performs inner product search. 
        #The "Flat" means it does a brute-force search (no indexing structure), and "IP" stands for inner product (Cosine)
        index = faiss.IndexFlatIP(d)
        index.add(X)
        sims, idxs = index.search(X, top_k + 1)
    else:
        sims, idxs = _knn_cosine_numpy(X, top_k + 1) #use numpy for unit tests

    #Build a graph from KNN results. We will use this graph to run community detection (Louvain) and compute drift scores.
    n = X.shape[0]
    G = nx.Graph()
    G.add_nodes_from(range(n)) # This creates an undirected weighted graph where each node = provider row index, edges = similarity above threshold
    # and the edge weights correspond to the cosine similarity scores.

    #neighbors (used for UI top_peers_str)
    #stores up to top_peers neighbor NPIs + similarity
    neighbors: Dict[str, List[Tuple[str, float]]] = {npis[i]: [] for i in range(n)}
    #used for Neo4j edges
    edges: List[Tuple[int, int, float]] = []
    # Populate edges from KNN results with thresholds
    for i in range(n):
        for r in range(1, top_k + 1):
            j = int(idxs[i, r])
            s = float(sims[i, r])
            if j == i or s < sim_threshold: #remove weak similarity links which helps help Louvain find meanginful groups
                continue
            G.add_edge(i, j, weight=s) #Graph edge
            edges.append((i, j, s)) #add record
            if len(neighbors[npis[i]]) < top_peers: #Peer list cap only up to top_peers
                neighbors[npis[i]].append((npis[j], s))

    #Community detection using Louvain
    part = community_louvain.best_partition(G, weight="weight", random_state=random_state) #weight uses cosine similarity as edge strength and makes the result repeatable when the algorithm has ties

    # Compute centroid-based "drift score" within Louvain community
    #need to normalize again b/c centroid averaging only makes sense if rows are comparable in scale
    Xn = _l2_normalize_rows(X)

    #Build community to member mapping from Louvain output. 
    comm_to_ids: Dict[int, List[int]] = {}
    for i, cid in part.items():
        comm_to_ids.setdefault(int(cid), []).append(int(i))

    #Compute a centroid for each community
    centroids: Dict[int, np.ndarray] = {}
    for cid, ids in comm_to_ids.items():
        c = Xn[ids].mean(axis=0) #selects member vectors in the community. mean(axis=0) computes the average vector
        c = c / (np.linalg.norm(c) or 1.0) #Normalize the centroid back to unit length so that dot product can be used.
        centroids[cid] = c

    #calculate drift score per provider based on cosine similarity to the community centroid.
    drift_score = np.zeros(n, dtype=np.float32)
    for i in range(n):
        cid = int(part.get(i, -1))
        c = centroids.get(cid)
        drift_score[i] = 1.0 if c is None else (1.0 - float(np.dot(Xn[i], c))) #cosine similarity between provider vector and its community centroid. 

    #Package provider output rows for Neo
    provider_rows: List[Tuple[str, int, float, str]] = []
    for i in range(n):
        npi = npis[i]
        cid = int(part.get(i, -1))
        top_peers_str = ", ".join([p for p, _ in neighbors[npi]])
        provider_rows.append((npi, cid, float(drift_score[i]), top_peers_str))

    return SimilarityResult(edges=edges, provider_rows=provider_rows, partition={int(k): int(v) for k, v in part.items()}) # ensure keys/vals are ints for neo
