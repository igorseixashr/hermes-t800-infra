#!/usr/bin/env python3
"""
Neo4j GraphRAG FastMCP Server
Expõe ferramentas de consulta ao Grafo de Conhecimento e Topologia de Infraestrutura para o Hermes Agent.
"""

import os
import sys
import json

try:
    from mcp.server.fastmcp import FastMCP
    from neo4j import GraphDatabase
except ImportError:
    print("[ERRO] Requer bibliotecas 'mcp' e 'neo4j'. Instale com: pip install mcp neo4j", file=sys.stderr)
    sys.exit(1)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "hermes_neo4j_password_change_me")

mcp = FastMCP("neo4j_graphrag")

def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

@mcp.tool()
def read_only_cypher(query: str) -> str:
    """
    Executa uma consulta Cypher somente-leitura no Neo4j para inspecionar topologia, hosts, IPs e documentos.
    Apenas comandos de leitura (MATCH, RETURN) são permitidos.
    """
    forbidden = ["CREATE", "DELETE", "SET", "REMOVE", "DROP", "MERGE"]
    upper_query = query.upper()
    for word in forbidden:
        if f" {word} " in f" {upper_query} ":
            return f"Erro: Apenas queries de leitura são permitidas. Comando proibido: {word}"

    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run(query)
            records = [record.data() for record in result]
            driver.close()
            return json.dumps(records, indent=2, default=str)
    except Exception as e:
        return f"Erro ao executar query Cypher: {str(e)}"

@mcp.tool()
def search_infra_topology(term: str) -> str:
    """
    Pesquisa por qualquer termo (IP, hostname, switch, VLAN ou documento de SOP) no grafo de infraestrutura.
    """
    cypher = """
    MATCH (n)
    WHERE (n:Host AND toLower(n.name) CONTAINS toLower($term))
       OR (n:IPAddress AND n.ip CONTAINS $term)
       OR (n:Subnet AND n.cidr CONTAINS $term)
       OR (n:Document AND (toLower(n.title) CONTAINS toLower($term) OR toLower(n.path) CONTAINS toLower($term)))
    OPTIONAL MATCH (n)-[r]-(connected)
    RETURN labels(n)[0] AS type,
           coalesce(n.name, n.ip, n.cidr, n.title) AS name,
           type(r) AS relationship,
           labels(connected)[0] AS connected_type,
           coalesce(connected.name, connected.ip, connected.cidr, connected.title) AS connected_target
    LIMIT 30
    """
    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run(cypher, term=term)
            records = [record.data() for record in result]
            driver.close()
            return json.dumps(records, indent=2, default=str)
    except Exception as e:
        return f"Erro na pesquisa de topologia: {str(e)}"

@mcp.tool()
def get_device_connections(device_name: str) -> str:
    """
    Obtém todas as conexões, IPs e documentos de SOP relacionados a um equipamento de rede ou servidor específico.
    """
    cypher = """
    MATCH (h:Host)
    WHERE toLower(h.name) = toLower($device_name) OR toLower(h.name) CONTAINS toLower($device_name)
    OPTIONAL MATCH (h)-[r]-(target)
    RETURN h.name AS host,
           type(r) AS rel,
           labels(target)[0] AS target_type,
           coalesce(target.name, target.ip, target.cidr, target.title) AS target_value
    """
    try:
        driver = get_driver()
        with driver.session() as session:
            result = session.run(cypher, device_name=device_name)
            records = [record.data() for record in result]
            driver.close()
            return json.dumps(records, indent=2, default=str)
    except Exception as e:
        return f"Erro ao obter conexões do equipamento: {str(e)}"

if __name__ == "__main__":
    mcp.run()
