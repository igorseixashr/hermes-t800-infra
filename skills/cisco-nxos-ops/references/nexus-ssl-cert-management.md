# Cisco Nexus SSL Certificate Management & Uptime Troubleshooting

## 1. Verifying Uptime & System Status
- `show version`: Check system uptime, software version, and hardware model.
- `show processes cpu`: Check CPU utilization.

## 2. SSL / NX-API Certificate Inspection
- `show nxapi`: Check NX-API status, HTTP/HTTPS ports, and certificate state.
- `show crypto ca certificates`: List installed PKI certificates and trustpoints.

## 3. Regenerating Factory Self-Signed Certificates
When Nessus/Tenable reports expired default factory certificates (`CN=nxos`), force regeneration on NX-OS without external CA certificates by toggling the service:
```cisco
configure terminal
! For NX-API:
no nxapi
nxapi
! For HTTP/HTTPS server:
no feature http-server
feature http-server
end
```

## 4. Zabbix Monitoring for SSL Expiry
To monitor certificate validity without external scripts on Zabbix 6.2+ / 7.0+:
- Use native `Script` item or `net.tcp.cert.get`.
- For older versions or network devices, use SSH Agent or External Check via OpenSSL:
  `echo | openssl s_client -connect <IP>:443 -servername <IP> 2>/dev/null | openssl x509 -noout -enddate`
