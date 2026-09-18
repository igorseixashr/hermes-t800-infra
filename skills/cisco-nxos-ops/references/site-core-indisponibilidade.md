# Troubleshooting Strategy: Site/CORE Indisponibilidade

## Checklist inicial
1. **Identificação**: Validar se o device é isolado ou se o site inteiro está offline.
2. **Conectividade**: 
   - Testar ping/SSH em dispositivos vizinhos no mesmo site (ex: CORE-2, Switch Agregador).
   - Verificar se há outros alertas de "Link Down" ou "BGP Peer Down" no monitoramento para aquele site específico.
3. **Gerência**: 
   - Verificar se o problema é restrito à rede de gerência (o tráfego de dados pode estar ok, mas a gerência via SSH falha).
   - Validar via NetBox a topologia de gerência (OOB).
4. **Escalonamento**: 
   - Se for ambiente físico (colo), preparar checklist para Equinix/Datacenter (LEDs de power/link).
