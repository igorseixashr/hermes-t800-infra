---
name: juniper-junos-bgp-ops
description: Operações e troubleshooting de BGP em roteadores Juniper Junos.
tags: [junos, bgp, routing, infra]
---

# Operações de BGP (Juniper Junos)

## Objetivo
Configurar, manipular preferências de rota e realizar troubleshooting de BGP em roteadores Junos (ex: MX204).

## Comandos de Troubleshooting
1. **Verificar rotas ativas:**
   `show route protocol bgp <prefixo>`
2. **Validar anúncios para vizinhos:**
   `show route advertising-protocol bgp <IP_VIZINHO>`
3. **Sessão BGP presa em `Connect`/`Active` (Falha L2/L3 / ARP):**
   Se o peer estiver preso em `Connect` ou `Active` com pacotes zerados:
   - Verificar reachability IP: `ping <IP_PEER> source <IP_LOCAL>`
   - Verificar resolução ARP (sub-redes diretas): `show arp no-resolve | match <IP_PEER>`
   - Verificar estado da interface/VLAN e policers de ARP: `show interfaces <interface> extensive`
4. **Limpar/Resetar sessão BGP:**
   `clear bgp neighbor <IP_VIZINHO>`

## Ajuste de Egress (Local Preference)
Para manipular a saída de tráfego, utilizamos `policy-statement` aplicada ao `import` do vizinho.
- **Aumentar preferência (Primário):** Importar política com `local-preference 300` (ou superior).
- **Diminuir preferência (Secundário):** Importar política com `local-preference 100` (ou inferior).

## Ajuste de Ingress (AS-Path Prepend)
Para manipular a entrada de tráfego, utilizamos `policy-statement` aplicada ao `export` do vizinho.
- Adicionar `as-path-prepend` na exportação torna o caminho menos atrativo para vizinhos (entrada secundária).

## Pitfalls
- Alterações no BGP são dinâmicas mas podem exigir `clear bgp neighbor` para recalculo imediato.
- Sempre utilize `commit confirmed X` (X minutos) para evitar bloqueio remoto.
- `local-preference` não é herdado automaticamente se houver rotas já instaladas na tabela; sempre rode o `clear bgp neighbor` após alterar políticas de importação.
