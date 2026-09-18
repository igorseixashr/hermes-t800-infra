try {
    var params = JSON.parse(value);
    var req = new CurlHttpRequest();
    var response;

    req.AddHeader('Content-Type: application/json');

    var payload = {
        "event_id": params.event_id || "",
        "hostname": params.hostname || "",
        "host_ip": params.host_ip || "",
        "trigger_name": params.trigger_name || "",
        "trigger_severity": params.trigger_severity || "",
        "trigger_status": params.trigger_status || ""
    };

    response = req.Post(params.url, JSON.stringify(payload));
    return 'OK';
} catch (error) {
    Zabbix.Log(3, '[Alert-Enricher] Erro: ' + error);
    throw 'Webhook erro: ' + error;
}
