# Validated G-code Cycle

For a medicine at `x_med`, `y_med`, the backend generates:

```gcode
G21
G90
G94
G1 X{x_med:.3f} Y{y_med:.3f} F600
G1 Z2.000 F200
G1 Z-2.000 F200
G1 X9.500 Y-2.900 F600
G1 Z2.000 F200
G1 Z-2.000 F200
G1 X0.000 Y0.000 F300
```

All machine constants come from `config/machine_config.json`.

