---
name: bgp-traffic-engineering
description: Engenharia de tráfego BGP em Junos
tags: [junos, bgp, traffic-engineering, routing]
---

# BGP Traffic Engineering (Junos)

## Objetivo
Alterar o link preferencial (Egress) para tráfego de saída utilizando manipulação de *Local Preference* no Junos.

## Procedimento (Política Nomeada)
Esta abordagem utiliza políticas nomeadas, permitindo alternar links apenas alterando o `import` no grupo BGP.

### 1. Criar Políticas (Policy-Options)
```junos
edit policy-options
# Alta preferência
set policy-statement LP-PREF-HIGH term LP from protocol bgp
set policy-statement LP-PREF-HIGH term LP then local-preference 300
set policy-statement LP-PREF-HIGH term LP then accept
set policy-statement LP-PREF-HIGH term LP then reject

# Baixa preferência
set policy-statement LP-PREF-LOW term LP from protocol bgp
set policy-statement LP-PREF-LOW term LP then local-preference 100
set policy-statement LP-PREF-LOW term LP then accept
set policy-statement LP-PREF-LOW term LP then reject
top
```

### 2. Alternar Links (Alterar 'import')
Para alterar o tráfego de um grupo BGP, modifique o `import`:
```junos
# Para Primário:
edit protocols bgp group <NOME_DO_GRUPO>
delete import
set import LP-PREF-HIGH
top

# Para Secundário:
edit protocols bgp group <NOME_DO_GRUPO>
delete import
set import LP-PREF-LOW
top

# Aplicar com segurança
commit confirmed 5
```

## Pitfalls
- **Assimetria:** Ao mover tráfego entre links de capacidades diferentes (ex: 10Gbps -> 1Gbps), monitore a interface imediatamente após o commit para evitar saturação e perda de pacotes (drops).
- **Commit Confirmed:** SEMPRE use `commit confirmed <minutos>` ao manipular BGP. Se você perder o acesso ao roteador (devido a mudança de rota), ele reverte automaticamente.
- **Entrada (Ingress):** Alterar `local-preference` afeta apenas a saída (Egress). Para influenciar a entrada (Ingress), considere usar `as-path-prepend` nos anúncios exportados.
