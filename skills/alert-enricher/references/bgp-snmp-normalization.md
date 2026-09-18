# BGP SNMP Normalization

Ao processar alertas do Zabbix (ou outros sistemas baseados em SNMP), é comum que o endereço IP do vizinho BGP venha "poluído" com prefixos de OID.

## OID Prefix: 1.4
Muitas MIBs de BGP (como a BGP4-MIB) estruturam as tabelas de vizinhos anexando o tipo de endereço e o comprimento antes do IP real.

- **Exemplo**: `1.4.10.152.255.138`
- **Análise**: 
  - `1`: Representa o `AddressType` (geralmente IPv4).
  - `4`: Representa o `Length` do endereço (4 octetos para IPv4).
  - `10.152.255.138`: O endereço IP real.

## Regex de Limpeza
Para extrair o IP limpo, utilize a seguinte lógica:
```regex
(?:peer|neighbor|bgp)[^\d]*([\d]{1,3}(?:\.[\d]{1,3}){3})
```
Ou, se souber que o prefixo é fixo `1.4.`:
```bash
echo "1.4.10.152.255.138" | sed 's/^1\.4\.//'
```

## Aplicação no NetBox
Sempre realize a limpeza antes de consultar o `mcp_netbox_get_ip_addresses`. Consultar o IP com o prefixo `1.4.` resultará em zero matches, atrasando o diagnóstico.
