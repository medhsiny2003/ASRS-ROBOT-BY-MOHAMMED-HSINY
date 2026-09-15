# SkyPharma ASRS

Python control software for a GRBL-based ASRS pharmacy medication retrieval robot.

This first implementation focuses on the backend and CLI:

- load machine constants from JSON
- manage medicines and dispensing history in SQLite
- generate the validated absolute-position G-code cycle
- stream commands to GRBL one line at a time
- update stock only after a successful dispense cycle

## Quick Start

```powershell
cd asrs_pharmacy_robot
python -m pytest
python app_cli.py --init-db --seed-test-medicine
python app_cli.py --list
```

With the robot connected:

```powershell
python app_cli.py --port COM5 --home
python app_cli.py --port COM5 --dispense 1
```

