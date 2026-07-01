# QuickLAN Share

A small LAN-only Flask app for sending files in either direction and sharing a
single live text pad across every connected browser.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://<this-computer's-LAN-IP>:57321` on another device connected to the
same network. To find the host address on Linux:

```bash
hostname -I
```

The server binds to every network interface on uncommon port `57321`. Override
it when needed:

```bash
QUICKLAN_PORT=49173 python app.py
```

Files are stored in `shared_files/`, and the shared pad persists in
`shared_pad.txt`. This app has no authentication, so only run it on a trusted
local network. You may need to allow the selected TCP port through the host
firewall.

## Test

```bash
python -m unittest discover -s tests
```
