#!/usr/bin/env python3
"""
Neo4j GraphRAG Ingestion
Lê arquivos Markdown da documentação (~/wiki) e constrói o grafo de conhecimento no Neo4j.
"""

import os
import sys
import re
from pathlib import Path

try:
    from neo4j import GraphDatabase
except ImportError:
    print("[ERRO] Biblioteca 'neo4j' não encontrada. Instale com: pip install neo4j")
    sys.exit(1)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "hermes_neo4j_password_change_me")
WIKI_DIR = Path(os.getenv("WIKI_OUTPUT_DIR", os.path.expanduser("~/wiki")))

IP_REGEX = re.compile(r'\b(?!(?:127|0)\.)(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')
CIDR_REGEX = re.compile(r'\b(?!(?:127|0)\.)(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)/(?:[1-2]?[0-9]|3[0-2])\b')
HOST_REGEX = re.compile(r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.(?:corp|local|internal|[a-z]{2,}))\b')
DEVICE_REGEX = re.compile(r'\b(sw-[a-z0-9-]+|rt-[a-z0-9-]+|fw-[a-z0-9-]+|srv-[a-z0-9-]+)\b', re.IGNORECASE)

def create_schema(session):
    print("[*] Criando índices e restrições no Neo4j...")
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.path IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (h:Host) REQUIRE h.name IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (i:IPAddress) REQUIRE i.ip IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Subnet) REQUIRE s.cidr IS UNIQUE")

def ingest_file(session, file_path):
    rel_path = str(file_path.relative_to(WIKI_DIR))
    title = file_path.stem.replace("_", " ")
    
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"[!] Erro ao ler {file_path}: {e}")
        return

    # Ingest Document node
    session.run(
        """
        MERGE (d:Document {path: $path})
        SET d.title = $title,
            d.updated_at = datetime()
        """,
        path=rel_path,
        title=title
    )

    # Extract IPs
    ips = set(IP_REGEX.findall(content))
    for ip in ips:
        session.run(
            """
            MATCH (d:Document {path: $path})
            MERGE (i:IPAddress {ip: $ip})
            MERGE (d)-[:MENTIONS]->(i)
            """,
            path=rel_path,
            ip=ip
        )

    # Extract Subnets
    subnets = set(CIDR_REGEX.findall(content))
    for cidr in subnets:
        session.run(
            """
            MATCH (d:Document {path: $path})
            MERGE (s:Subnet {cidr: $cidr})
            MERGE (d)-[:MENTIONS]->(s)
            """,
            path=rel_path,
            cidr=cidr
        )

    # Extract Hostnames / Devices
    hosts = set(HOST_REGEX.findall(content)).union(set(DEVICE_REGEX.findall(content)))
    for host in hosts:
        host_name = host.lower()
        session.run(
            """
            MATCH (d:Document {path: $path})
            MERGE (h:Host {name: $name})
            MERGE (d)-[:MENTIONS]->(h)
            """,
            path=rel_path,
            name=host_name
        )

def main():
    if not WIKI_DIR.exists():
        print(f"[AVISO] Diretório de wiki '{WIKI_DIR}' não existe. Execute o confluence_sync.py primeiro.")
        return

    print(f"[*] Conectando ao Neo4j em {NEO4J_URI}...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
    except Exception as e:
        print(f"[ERRO] Falha ao conectar no Neo4j: {e}")
        sys.exit(1)

    with driver.session() as session:
        create_schema(session)
        
        md_files = list(WIKI_DIR.glob("**/*.md"))
        print(f"[*] Encontrados {len(md_files)} arquivos Markdown para ingestão...")
        
        for idx, f in enumerate(md_files, 1):
            ingest_file(session, f)
            if idx % 20 == 0 or idx == len(md_files):
                print(f"  -> Processados {idx}/{len(md_files)} documentos...")

    driver.close()
    print("[✓] Ingestão no Grafo Neo4j concluída com sucesso!")

if __name__ == "__main__":
    main()
