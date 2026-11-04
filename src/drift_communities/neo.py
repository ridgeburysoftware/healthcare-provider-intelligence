from __future__ import annotations

import os
from typing import Any, Dict, List

import streamlit as st


def _parse_auth_blob(raw: str) -> tuple[str, str]:
    raw = (raw or "").strip()
    if "/" in raw:
        user, pwd = raw.split("/", 1)
        return user.strip(), pwd.strip()
    if ":" in raw:
        user, pwd = raw.split(":", 1)
        return user.strip(), pwd.strip()
    raise ValueError("NEO4J_AUTH must be in 'user/password' format.")


@st.cache_resource(show_spinner=False)
def neo_driver():
    from neo4j import GraphDatabase  # type: ignore

    uri = os.getenv("NEO4J_URI", "bolt://127.0.0.1:17687")
    auth_blob = os.getenv("NEO4J_AUTH", "").strip()
    pwd = os.getenv("NEO4J_PASS", "").strip()
    user = os.getenv("NEO4J_USER", "neo4j").strip() or "neo4j"

    if auth_blob:
        user_from_blob, pwd_from_blob = _parse_auth_blob(auth_blob)
        user = user_from_blob or user
        pwd = pwd_from_blob

    if not pwd:
        raise RuntimeError("Missing Neo4j credentials. Set NEO4J_AUTH or NEO4J_PASS.")

    return GraphDatabase.driver(uri, auth=(user, pwd))


def run_cypher(q: str, **params) -> List[Dict[str, Any]]:
    drv = neo_driver()
    with drv.session() as s:
        return [dict(r) for r in s.run(q, **params)]
