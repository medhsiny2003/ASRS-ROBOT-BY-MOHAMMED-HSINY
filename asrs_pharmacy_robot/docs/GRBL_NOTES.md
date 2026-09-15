# GRBL Notes

- Firmware target: GRBL 1.1h on Arduino UNO.
- CoreXY is enabled in `config.h`.
- `HOMING_FORCE_SET_ORIGIN` is enabled.
- `VARIABLE_SPINDLE` is disabled so the CNC Shield V3 Z limit pin works correctly.
- Homing order is Z, then X, then Y.
- After `$H`, machine position should report `MPos:0.000,0.000,0.000`.
- The backend uses absolute mode (`G90`) and machine coordinates captured after homing.

