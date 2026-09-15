# SkyPharma ASRS Software Suite

Python control software for a GRBL-based ASRS (Automated Storage and Retrieval System) pharmacy medication robot.

## Features

- **Admin Supervision & SCADA GUI (PyQt6)**: Real-time machine monitoring, Jog controls, automatic homing, inventory management with spatial coordinates $(X, Y)$, and G-code console.
- **Client Web Portal (Streamlit)**: Live synchronized catalog, stock tracking, category filtering, and instant order placement.
- **SQLite Database**: Persistent relational schema storing medicines, coordinates, stock levels, and dispensing history.
- **GRBL Motion Control Engine**: Trajectory generation with safety clearance, USB serial streaming, and finite state machine.

## Quick Start

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

### 2. Run Admin SCADA Interface

```powershell
python app.py
```

### 3. Run Client Web Portal

```powershell
streamlit run client_app.py
```

### 4. CLI / Automated Testing

```powershell
python -m pytest
python app_cli.py --list
python app_cli.py --port COM3 --home
python app_cli.py --port COM3 --dispense 1
```
