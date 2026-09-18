# Grafana Time Series Configuration for Binary Reachability (UP/DOWN)

## Overview
When monitoring device reachability (`Reachable` metric returning `1` for UP and `0` for DOWN) in Grafana with Zabbix:

1. **Visualization Panel**: `Time series`
2. **Line Interpolation**: `Step before` (creates clean square waves for binary state changes).
3. **Decimals**: `0` (cleans up Y-axis to show only `0` and `1` / `DOWN` and `UP`).
4. **Value Mappings**:
   - `1` ➔ `UP`
   - `0` ➔ `DOWN`
5. **Thresholds**:
   - `Base` (`<= 0`) ➔ Red (DOWN)
   - `1` ➔ Green (UP)
6. **Color Scheme & Gradient**:
   - Color scheme: `From thresholds (by value)`
   - Gradient mode: `Scheme` (paints line and fill according to active threshold).
7. **Text / Banner Panels**:
   - Always put Markdown/HTML content in the central **Content** editor, **not** in the sidebar **Title** field, to avoid `Error loading: text`.
8. **Dashboard Layout (Rows)**:
   - Use collapsible **Rows** to group panels by site/datacenter (e.g., Atlanta, Chicago, Ascenty, EQX).
