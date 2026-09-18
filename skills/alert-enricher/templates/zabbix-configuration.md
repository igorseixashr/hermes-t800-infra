# Zabbix Webhook Configuration for Alert Enricher

To integrate Zabbix with the Hermes Alert Enricher, configure a Media Type of type "Webhook" with the following settings:

## Parameters
| Name | Value |
| :--- | :--- |
| hostname | {HOST.NAME} |
| host_ip | {HOST.IP} |
| trigger_name | {TRIGGER.NAME} |
| trigger_severity | {TRIGGER.SEVERITY} |
| trigger_status | {TRIGGER.STATUS} |
| trigger_description | {TRIGGER.DESCRIPTION} |
| alert_message | {ALERT.MESSAGE} |
| item_name | {ITEM.NAME} |
| item_value | {ITEM.VALUE} |
| event_id | {EVENT.ID} |

## Script (Javascript snippet)
```javascript
try {
    var params = JSON.parse(value),
        req = new HttpRequest(),
        resp;

    req.addHeader('Content-Type: application/json');
    
    // Optional: Add signature if a secret is used
    // req.addHeader('X-Hermes-Signature: ' + make_hmac(value, '<SECRET>'));

    resp = req.post('http://<HERMES_IP>:8644/webhooks/zabbix-enricher', JSON.stringify(params));

    if (req.getStatus() !== 200) {
        throw 'Response code: ' + req.getStatus();
    }

    return 'OK';
} catch (error) {
    Zabbix.log(3, 'Hermes notification failed: ' + error);
    throw 'Hermes notification failed: ' + error;
}
```

## URL
`http://<HERMES_IP>:8644/webhooks/zabbix-enricher`
