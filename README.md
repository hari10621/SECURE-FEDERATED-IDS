# SecureFed-IDS

SecureFed-IDS is a local web dashboard for training a federated intrusion detection model and reviewing its predictions. Follow this guide to run it on Windows 11. If the project is already installed, skip to [Start the project](#start-the-project).

## First-time installation

Install 64-bit Python 3.12 and Node.js 22.12 or newer with npm. Open a fresh Windows PowerShell window and check the versions.

~~~powershell
python --version
node --version
npm.cmd --version
~~~

Run the following commands. If your checkout is elsewhere, change the folder on the first line.

~~~powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r .\requirement.txt
npm.cmd ci --prefix .\web\frontend
~~~

The launcher finds the project environment automatically. The complete Python dependency list is in [requirement.txt](requirement.txt). Windows Native Simulation runs directly on Windows. The optional live capture mode requires the Npcap driver. For the optional Linux lab, see [Mininet setup](memory.md#isolated-sdn-network).

## Start the project

~~~powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
.\start_all.ps1
~~~

Wait for the launcher to print the dashboard URL. Open [SDN Network](http://127.0.0.1:5173/sdn) for the Windows simulator. To begin training a model, open [Datasets](http://127.0.0.1:5173/datasets) and follow the [GUI walkthrough](memory.md#demonstrate-verified-learning-in-the-browser).

To verify the backend separately, open its [health endpoint](http://127.0.0.1:8000/api/v1/health).

### Start each service in its own terminal

For visible server logs, open two PowerShell windows in the project folder. Run this in the first window:

~~~powershell
.\start_backend.ps1
~~~

Run this in the second window:

~~~powershell
.\start_frontend.ps1
~~~

## Stop or restart

From the project folder, run:

~~~powershell
.\stop_services.ps1
~~~

To restart, run the combined launcher again. Stopping the services preserves your datasets, clients, models, and training history.

## Startup troubleshooting

| What you see | What to do |
| --- | --- |
| PowerShell cannot find the start script | Change to the folder containing this README and run the script command shown above. |
| An empty path error or a missing Python module named app | Run the whole backend or combined launcher script from the project root. It selects the backend working directory for you. |
| A missing Python package or Vite dependency | Rerun the pip and npm installation commands and check that both finish successfully. |
| The launcher reports an older backend on port 8000 | Run the stop script, then the start script. If startup still fails, open the log file named in the error message. |
