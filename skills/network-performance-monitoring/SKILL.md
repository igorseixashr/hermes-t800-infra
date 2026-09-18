---
name: network-performance-monitoring
description: Medir performance de rede com iperf3, owamp e twamp.
---
# network-performance-monitoring skill

## Description
Medir a performance de rede (latência, jitter, perda, throughput) entre nós usando ferramentas padrão de indústria como iperf3, owamp e twamp. Cobre desde a instalação e compilação até o diagnóstico.

## When to Use
Use esta skill quando `ping` (ICMP) for insuficiente e você precisar de métricas de rede mais precisas e detalhadas, como:
- Latência unidirecional (one-way) e bidirecional (two-way).
- Jitter (variação na latência).
- Perda de pacotes em fluxos UDP.
- Throughput (largura de banda) máximo entre dois pontos.

É a skill correta para implementar malhas de monitoramento inspiradas em `perfSONAR`.

## Prerequisites
As ferramentas precisam ser instaladas nos probes (nós de medição).

### iperf3
Para Red Hat/Rocky Linux/Oracle Linux:
```bash
sudo dnf install -y epel-release
sudo dnf install -y iperf3
```

### OWAMP/TWAMP (owping, twping, owampd)
Estes geralmente precisam ser compilados do código-fonte.

1.  **Instalar dependências de compilação:**
    ```bash
    sudo dnf install -y git gcc make automake autoconf libtool
    ```

2.  **Clonar o repositório (com submódulos):**
    A compilação pode falhar se o diretório de build estiver em um filesystem com a flag `noexec` (como `/tmp` frequentemente está). Clone em um diretório seguro, como `~/build`.
    ```bash
    mkdir -p ~/build
    cd ~/build
    # A flag --recurse-submodules é CRÍTICA para evitar falhas de compilação
    git clone --recurse-submodules https://github.com/danos/owamp.git
    cd owamp
    ```

3.  **Compilar e instalar:**
    ```bash
    # Gera os scripts de configuração
    ./bootstrap
    # Configura o build
    ./configure
    # Compila
    make
    # Instala os binários em /usr/local/bin
    sudo make install
    ```
4.  **Verificar a instalação:**
    ```bash
    which owping twping owampd iperf3
    ```

## Procedure

### Teste de Throughput (iperf3)
Requer um cliente e um servidor.

1.  **No nó Servidor:**
    ```bash
    # Inicia o iperf3 em modo servidor, escutando por testes
    iperf3 -s
    ```

2.  **No nó Cliente:**
    ```bash
    # Inicia um teste de 10 segundos contra o servidor
    iperf3 -c <IP_DO_SERVIDOR>
    ```

### Teste de Latência Unidirecional (OWAMP)
Requer um cliente (`owping`) e um servidor (`owampd`).

1.  **No nó Servidor:**
    O `owampd` não deve rodar como root. Inicie-o com um usuário de serviço (ex: `infra-network`) e especifique um diretório para o arquivo de PID.
    ```bash
    # Mata qualquer instância anterior
    sudo pkill -u infra-network owampd || true
    sleep 1
    # Inicia com o usuário correto e diretório de PID em /tmp
    sudo /usr/local/bin/owampd -R /tmp -U infra-network
    # Verifica se está rodando
    pgrep -u infra-network owampd
    ```

2.  **No nó Cliente:**
    ```bash
    # Envia 5 pacotes com 100ms de intervalo
    owping -c 5 -i 0.1 <IP_DO_SERVIDOR>
    ```
    O resultado conterá as métricas de `Median` (latência), `Jitter` e `Packet loss`.

## Pitfalls & Troubleshooting

-   **Compilação falha com `Permission denied` em `./bootstrap`:** O diretório de compilação está em um filesystem `noexec`. Mova para `~/build` ou outro local executável.
-   **Compilação falha com erro em `I2util`:** O clone foi feito sem a flag `--recurse-submodules`. Delete o diretório e clone novamente com a flag.
-   **`owampd` não inicia:**
    -   **`command not found`:** O `sudo` pode não ter `/usr/local/bin` no `secure_path`. Use o caminho completo: `sudo /usr/local/bin/owampd`.
    -   **`Permission denied` ao criar PID:** O daemon tentou escrever em um diretório sem permissão. Use a flag `-R /tmp` para usar um diretório gravável.
    -   **`Running as root is folly`:** O daemon se recusa a rodar como root. Use a flag `-U <username>` para especificar um usuário não-privilegiado.
-   **`owping` falha com `Unable to open control connection`:** Um firewall está bloqueando a comunicação entre o cliente e o servidor.
    -   **Diagnóstico:** Use `nmap -p 861 <IP_DO_SERVIDOR>`. Se o estado for `filtered`, é um firewall.
    -   **Solução:** Peça a liberação da origem para o destino nas portas **TCP/861** (controle) e **UDP/8760-9960** (teste).
