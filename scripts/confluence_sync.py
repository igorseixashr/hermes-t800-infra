#!/usr/bin/env python3
"""
Confluence Space Exporter & Sync
Sincroniza páginas de espaços do Confluence para arquivos Markdown locais (~/wiki/<SPACE>/).
"""

import os
import sys
import json
import re
import html
import urllib.request
import urllib.error
import base64
from pathlib import Path

# Configurações via variáveis de ambiente
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL", "").rstrip("/")
CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME", "")
CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "")
SPACES = [s.strip() for s in os.getenv("CONFLUENCE_SPACES", "INFRA").split(",") if s.strip()]
OUTPUT_DIR = Path(os.getenv("WIKI_OUTPUT_DIR", os.path.expanduser("~/wiki")))

def get_auth_header():
    if not CONFLUENCE_USERNAME or not CONFLUENCE_API_TOKEN:
        print("[ERRO] CONFLUENCE_USERNAME ou CONFLUENCE_API_TOKEN não definidos no ambiente.")
        sys.exit(1)
    auth_str = f"{CONFLUENCE_USERNAME}:{CONFLUENCE_API_TOKEN}".encode("utf-8")
    return "Basic " + base64.b64encode(auth_str).decode("utf-8")

def clean_filename(name):
    clean = re.sub(r'[\\/*?:"<>|]', "_", name)
    return clean[:100].strip()

def html_to_markdown(html_text):
    if not html_text:
        return ""
    # Converte títulos
    text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', html_text, flags=re.I|re.S)
    text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', text, flags=re.I|re.S)
    text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', text, flags=re.I|re.S)
    text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', text, flags=re.I|re.S)
    # Converte formatação
    text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text, flags=re.I|re.S)
    text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text, flags=re.I|re.S)
    text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text, flags=re.I|re.S)
    text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text, flags=re.I|re.S)
    # Converte blocos de código
    text = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n', text, flags=re.I|re.S)
    # Converte parágrafos e quebras
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<p[^>]*>(.*?)</p>', r'\n\1\n', text, flags=re.I|re.S)
    # Converte listas
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1', text, flags=re.I|re.S)
    # Remove tags restantes
    text = re.sub(r'<[^>]+>', '', text)
    # Decodifica entidades HTML
    text = html.unescape(text)
    # Normaliza quebras de linha múltiplas
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def fetch_pages(space_key):
    print(f"[*] Sincronizando espaço Confluence: {space_key}...")
    dest_dir = OUTPUT_DIR / space_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    headers = {
        "Authorization": get_auth_header(),
        "Accept": "application/json"
    }
    
    start = 0
    limit = 25
    count = 0
    
    while True:
        url = f"{CONFLUENCE_URL}/rest/api/content?spaceKey={space_key}&type=page&expand=body.storage,version&start={start}&limit={limit}"
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[!] Erro ao consultar {url}: {e}")
            break
            
        results = data.get("results", [])
        if not results:
            break
            
        for page in results:
            page_id = page.get("id")
            title = page.get("title", f"page_{page_id}")
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            
            md_content = html_to_markdown(body_html)
            filename = f"{clean_filename(title)}.md"
            file_path = dest_dir / filename
            
            frontmatter = f"""---
title: "{title}"
confluence_id: "{page_id}"
space: "{space_key}"
---

# {title}

"""
            with open(file_path, "w", encoding="utf-8") as wf:
                wf.write(frontmatter + md_content)
            count += 1
            
        start += len(results)
        if len(results) < limit:
            break

    print(f"[✓] Concluído espaço {space_key}: {count} páginas salvas em {dest_dir}")

def main():
    if not CONFLUENCE_URL:
        print("[ERRO] CONFLUENCE_URL não configurada.")
        print("Defina as variáveis no arquivo .env ou exporte-as no shell:")
        print("  export CONFLUENCE_URL='https://sua-empresa.atlassian.net/wiki'")
        print("  export CONFLUENCE_USERNAME='seu_usuario'")
        print("  export CONFLUENCE_API_TOKEN='seu_token'")
        print("  export CONFLUENCE_SPACES='INFRA,SOP'")
        sys.exit(1)
        
    for space in SPACES:
        fetch_pages(space)

if __name__ == "__main__":
    main()
