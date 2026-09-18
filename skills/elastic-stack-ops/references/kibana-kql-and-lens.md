# Kibana KQL Querying and Lens Visualization Reference

## KQL Query Patterns in Discover

1. **Filtering Destination & Excluding Multiple Source IPs:**
   When excluding multiple IPs or entities, use parentheses and `or` (NOT `and`), as a packet/log cannot originate from multiple IPs simultaneously:
   ```kql
   destination.ip : "10.220.64.120" AND NOT source.ip : ("10.10.4.132" or "10.30.2.12" or "10.30.2.13" or "10.30.2.14")
   ```

2. **CIDR Network Exclusion:**
   ```kql
   destination.ip : "10.220.65.12" AND NOT destination.ip : 10.30.2.0/24
   ```

## Creating Bar Charts in Kibana (Lens)

1. Build and test your query in **Discover**.
2. Switch to **Lens** (Visualize Library / Create visualization).
3. Set chart type to **Bar**.
4. Configure **Y-Axis** with metric (`Count`).
5. Configure **X-Axis** with dimension/grouping field (e.g. `source.ip`, `destination.port`, `@timestamp`).
