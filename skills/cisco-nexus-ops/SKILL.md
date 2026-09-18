---
name: cisco-nexus-ops
description: Procedures for managing, troubleshooting, and configuring Cisco Nexus network infrastructure.
---

### Standard Procedures
- **Conexão SSH**: Sempre use parâmetros de segurança para dispositivos legados com chaves host RSA pequenas.
- **Validação de Certificados HTTPS/NX-API**: Use `show nxapi` e `show crypto ca certificates` para inspecionar certificados de gerência auto-assinados de fábrica (`CN=nxos`).

### Pitfalls & Troubleshooting
- **Erro 'Bad server host key: Invalid key length'**: Ocorre em switches Nexus com chaves RSA antigas (pequenas).
  - **Solução**: Use `ssh -o RequiredRSASize=1024 -o IdentitiesOnly=yes -o PubkeyAuthentication=no <user>@<ip> "<comando>"`.
- **Desbalanceamento vPC + VMware**: Se o VMware estiver em modo 'Ativo-Standby', o balanceamento do switch (hash LACP) torna-se ineficaz para fluxos únicos (como replicação SQL), pois o tráfego é "pinado" no uplink ativo. A solução é mudar o teaming do VMware para LACP ou 'Route based on IP Hash'.
- **Ferramentas de Diagnóstico**:
  - `show port-channel load-balance` (valida o hash global).
  - `show interface port-channel X counters` (checa drops e erros).
  - `show interface port-channel X` (checa MTU e status).