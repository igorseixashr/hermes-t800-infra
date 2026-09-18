# Partner/Legacy Device Investigation (ALP/B2B)

Este guia trata da investigação de alertas em equipamentos que não estão cadastrados como objetos `Device` no NetBox, comum em cenários de integração B2B e hardware legado em datacenters de parceiros (ex: Tivit, DXC, Algar).

## 1. Identificação (ALP - Autorizador Legado de Parceiro)
O sufixo `-ALP-X` geralmente indica roteadores legados atendendo bandeiras (Sodexo, Alelo, Ticket).
- **NetBox Gap**: Frequentemente esses dispositivos existem apenas como IPs em Loopbacks ou Subinterfaces nos Core Switches, sem um objeto `Device` próprio.
- **Pivoteamento**: Se a busca por device falhar, use `mcp_netbox_search_objects` nos endpoints `ipam/ip-addresses` e `ipam/prefixes` usando o nome do parceiro.

## 2. Fontes de Verdade Alternativas
Se o inventário estiver incompleto:
1. **Confluence**: Busque por anexos `.xlsx` ou `.pdf` com nomes como "Equipamentos Monitoração" ou "Port-Map". Estes arquivos costumam conter o mapeamento físico que não foi migrado para o NetBox.
2. **Jira**: Busque pelo hostname em projetos de Redes (`FPDN`, `FPCONECTIV`). Comentários em cards antigos (ex: `FPDN-1495`) frequentemente revelam que o equipamento está "congelado" (EoL) e não deve ser atualizado.

## 3. Validação de Conectividade
- **Heartbeat IPs**: Verifique IPs na faixa `10.254.254.0/24`. São comumente usados para monitoramento de disponibilidade (Keepalive).
- **BGP State**: Como esses roteadores são "caixas pretas" para a corp, a saúde do serviço é medida pelo estado do peer BGP nos Cores locais (ex: `EQX-RJ2-ADQ-CORE-01`).
    - Estado `Active (3)`: O Core está tentando abrir o socket TCP, mas não recebe resposta (queda de transporte/link).
    - Estado `Idle`: Peer administrativamente down ou falha crítica de roteamento interno.

## 4. Troubleshooting de Transporte
- Verifique circuitos no NetBox com o nome do parceiro ou operadora (ex: Algar).
- Se ambos os membros do par redundante (ALP-1 e ALP-2) caírem simultaneamente, o problem é quase certamente no transporte (Golden Jumper, Link UTP, Switch de Acesso do Parceiro) ou energia no rack remoto.

## 5. SSH para Ativos Legados no Rocky 9 / RHEL 9
Ao tentar conectar via SSH a equipamentos antigos (como o Cisco 1905), sistemas modernos como o Rocky/RHEL 9 barram algoritmos de criptografia mais fracos (SHA-1, assinaturas ssh-rsa, ciphers CBC) a nível de Openssl/libcrypto, retornando erros fatais como:
`ssh_dispatch_run_fatal: Connection to <IP> port 22: error in libcrypto`

### Bypass de libcrypto por variável de ambiente
Para contornar isso temporariamente sem enfraquecer a política global de segurança do SO (`update-crypto-policies`), execute o comando injetando `OPENSSL_ENABLE_SHA1_SIGNATURES=1` e especificando os algoritmos legados via parâmetros adicionais do OpenSSH:

```bash
env OPENSSL_ENABLE_SHA1_SIGNATURES=1 ssh \
  -o StrictHostKeyChecking=no \
  -o KexAlgorithms=diffie-hellman-group1-sha1,diffie-hellman-group14-sha1 \
  -o HostKeyAlgorithms=ssh-rsa \
  -o PubkeyAcceptedAlgorithms=ssh-rsa \
  -o Ciphers=aes128-cbc,aes256-cbc,3des-cbc \
  svc-backup@<IP_GERENCIA>
```

### Script de Automação PTY (Sem Netmiko/Paramiko/Sshpass)
Se o ambiente de execução não possuir dependências externas (como `netmiko`, `paramiko` ou `sshpass`), utilize o script Python nativo abaixo para simular um pseudo-terminal (PTY), interceptar o prompt e injetar a senha de forma interativa e robusta:

```python
import os
import sys
import pty
import select

def execute_legacy_ssh(host, username, password, command):
    # Força a libcrypto do Rocky 9 a permitir assinaturas SHA-1
    os.environ["OPENSSL_ENABLE_SHA1_SIGNATURES"] = "1"
    
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "KexAlgorithms=diffie-hellman-group1-sha1,diffie-hellman-group14-sha1",
        "-o", "HostKeyAlgorithms=ssh-rsa",
        "-o", "PubkeyAcceptedAlgorithms=ssh-rsa",
        "-o", "Ciphers=aes128-cbc,aes256-cbc",
        f"{username}@{host}",
        command
    ]
    
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("ssh", ssh_cmd)
        sys.exit(1)
        
    output = []
    password_sent = False
    
    while True:
        r, w, x = select.select([fd], [], [], 10)
        if not r:
            break
        try:
            data = os.read(fd, 4096)
        except OSError:
            break
        if not data:
            break
            
        chunk = data.decode("utf-8", "ignore")
        output.append(chunk)
        
        if "password:" in chunk.lower() and not password_sent:
            os.write(fd, (password + "\n").encode())
            password_sent = True
            
    os.waitpid(pid, 0)
    return "".join(output)
```
