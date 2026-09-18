# Confluence Sync Workflow Ref

Para espaços do Confluence, o processo de exportação segue:
1. Listar árvore via confluence_get_space_page_tree.
2. Ler conteúdo de cada página via confluence_get_page (convert_to_markdown=True).
3. Salvar como Markdown em diretório local.
4. Adicionar YAML frontmatter com o título da página.

Exemplo de automação de limpeza de meta-dados:
```bash
# Adiciona frontmatter se faltando
for f in *.md; do
    if ! head -n 1 "$f" | grep -q "---"; then
        title=$(grep -m 1 "^# " "$f" | sed 's/# //')
        if [ -z "$title" ]; then title="Untitled"; fi
        printf "---\ntitle: \"%s\"\n---\n\n" "$title" | cat - "$f" > "$f.new" && mv "$f.new" "$f"
    fi
done
```
