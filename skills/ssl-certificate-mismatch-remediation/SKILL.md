---
name: ssl-certificate-mismatch-remediation
description: Protocolo para diagnóstico e correção de vulnerabilidades de "SSL Certificate Mismatch" (Hostname/IP/SAN).
---

# Protocolo de Correção: SSL Certificate Mismatch

Este skill define o padrão de operação para diagnosticar e corrigir vulnerabilidades de "Hostname Mismatch" em endpoints.

## 1. Diagnóstico Inicial
Antes de alterar qualquer certificado, valide o que o serviço está apresentando:

### Linux / Remoto (via SSH)
```bash
# Verifica o que o certificado reporta
openssl s_client -connect <IP>:<PORT> -showcerts </dev/null 2>/dev/null | openssl x509 -noout -text | grep -E "DNS:|Subject:|Common Name"
```

### Windows / SolarWinds (via PowerShell)
1. Listar certificados instalados:
   ```powershell
   Get-ChildItem -Path "Cert:\LocalMachine\My" | Select-Object Subject, NotAfter, Thumbprint
   ```
2. Verificar o que está vinculado ao serviço (BINDING):
   ```powershell
   netsh http show sslcert
   ```

## 2. Ações de Correção (Thesis-Driven)
*   **Ação Primária (Produtivo):** Gerar CSR com SAN/CN correto e substituir no store/binding.
*   **Ação Secundária (SolarWinds/Workaround):** Revisar bindings no IIS (NetPerfMon site).
*   **Ação de Conformidade (Isolamento):** Se o ativo for backend interno e não exposto a usuários, considere adicionar exceção no scanner (Nessus/Zabbix) em vez de renovação manual constante de autoassinados.

## 3. Pitfalls Comuns
*   **Get-PfxCertificate vs Get-ChildItem:** `Get-PfxCertificate` lê arquivos `.pfx` no disco; para consultar o store do Windows, use sempre `Get-ChildItem Cert:\LocalMachine\My`.
*   **Orion Configuration Wizard:** Rodar sem snapshot prévio em ambientes SolarWinds é um risco operacional alto.
*   **False Positives:** Certificados internos em redes isoladas often disparam esses alertas. Valide o risco antes da mudança.
