try {
    var params = JSON.parse(value);
    var req = new CurlHttpRequest();
    var response;

    req.AddHeader('Content-Type: application/json');

    // Field mapping for Alert Enricher
    var payload = {
        "event_id": params.event_id || "",
        "hostname": params.hostname || "",
        "host_ip": params.host_ip || "",
        "trigger_name": params.trigger_name || "",
        "trigger_severity": params.trigger_severity || "",
        "trigger_status": params.trigger_status || "",
        "trigger_description": params.trigger_description || "",
        "alert_message": params.alert_message || "",
        "item_name": params.item_name || "",
        "item_value": params.item_value || ""
    };

    Zabbix.Log(4, '[Alert-Enricher] Sending payload to ' + params.url);
    response = req.Post(params.url, JSON.stringify(payload));
    Zabbix.Log(4, '[Alert-Enricher] Response: ' + response);

    return 'OK';
}
catch (error) {
    Zabbix.Log(3, '[Alert-Enricher] Critical Error: ' + error);
    throw 'Webhook error: ' + error;
}
