# Sodexo Legacy Infrastructure (ALP-1 / ALP-2)

Detalhes operacionais e riscos associados aos roteadores legados que atendem a Sodexo (Pluxee).

## Devices
| Hostname | Primary IP (Loopback) | Heartbeat IP | Location |
| :--- | :--- | :--- | :--- |
| `SODEXO-ALP-1` | `10.166.32.116` | `10.254.254.113` | Tivit/DXC (Parceiro) |
| `SODEXO-ALP-2` | `10.245.254.114` | `10.254.254.114` | Tivit/DXC (Parceiro) |

## Operational Status & Risks
- **End-of-Life (EoL)**: Dispositivos fora de suporte e garantia.
- **High Risk Update**: Conforme card **FPDN-1495**, a aplicação de correções ou updates de software está **suspensa**. O risco de o equipamento não retornar após um reboot é alto.
- **Substitution Project**: Monitorado pelo card **FPDN-5025** ("Troca dos Roteadores Pluxee").
- **External Dependencies**: Localizados em ambiente de parceiro. Quedas simultâneas de ALP-1 e ALP-2 geralmente indicam falha no transporte (**Algar**) ou na infraestrutura física do parceiro (Tivit/DXC).

## Diagnostics
- **BGP Peering**: O peering ocorre via VLAN 1746 (SODEXO-ALGAR-DXC-@1) nos cores do RJ2.
- **Connectivity Failures**: Se ambos os IPs pararem de responder, acionar imediatamente a sustentação de rede para validar links Algar e infra Tivit.
