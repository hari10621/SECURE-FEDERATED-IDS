# SecureFed-IDS

SecureFed-IDS is a local research console for training a federated intrusion detector on labeled SDN flow records. It supports sample-weighted plaintext FedAvg and TenSEAL CKKS aggregation for the GRU workflow described in *A Secure and Privacy-Preserving Federated Learning-Based Intrusion Detection System for SDN Networks Using Homomorphic Encryption*. The Windows demo runs the API, training workers and dashboard on one machine. The coordinator reads the uploaded CSV and distributes training shards, so it has access to the raw data. The bundled CSVs contain generated traffic examples. Performance on the original research datasets requires separate evaluation.

## Windows 11 native network tutorial

**Start here for the Windows demonstration.** The default **SDN Network** engine runs a graph, forwarding rules, virtual frames and counters inside the FastAPI process. It needs ordinary Windows user permissions. Mininet and Npcap are optional. Model training still uses the existing GRU workers, saved preprocessing, SQLite storage, FedAvg or CKKS, and model validation gate.

On a new installation, install Python 3.12 and a Node.js version supported by the frontend's Vite dependency. From Windows PowerShell run:

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
python -m venv web/backend/.venv-tf
& web/backend/.venv-tf/Scripts/python.exe -m pip install -r web/backend/requirements-training.txt
npm.cmd ci --prefix web/frontend
```

For encrypted aggregation, also install `web/backend/requirements-crypto.txt` into the same environment. On an existing installation, start at the following commands:

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
.\start_all.ps1
```

Open [SDN Network](http://127.0.0.1:5173/sdn). Use `.\stop_services.ps1` from the same directory to stop the project servers. If an older backend already owns port 8000, stop it and run the launcher again. To use separate loopback ports, set `SECUREFED_API_PORT` and `SECUREFED_UI_PORT` in the launcher and stop shells. Startup errors include the path to the service log.

### Demonstrate verified learning in the browser

1. In **Datasets**, upload `datasets/insdn_compact_1k.csv`, select **InSDN** and label column **Label**. In **Central Model**, create a uniquely named random-initialized V0 using that dataset. Existing models can be selected for inspection.
2. In **Federated Clients**, assign two distinct workers to that model. Give each an organization, select its local dataset, set local epochs to **1**, and use **Train on assignment**. Leave the optional Mininet host blank. Wait for both jobs to succeed. In **Federated Training**, select that model, V0, both workers and the stored-update aggregation operation. Review the resulting candidate in **Central Model**. Deploy only after validation passes and click **Synchronize workers**. Check both acknowledgements.
3. In **SDN Network**, keep **Windows Native Simulation**, select **single**, **3 hosts**, and subnet **10.0.0.0/24**. Click **Create network**, then **start**. Select h1 in **Inspect node**, select the first worker under **Assign federated client**, then **Save host mapping**. Repeat for h2 and the second worker. Use h3 as the source. The inspector shows worker identity, organization, dataset and synchronization evidence.
4. Choose h3 as **Source host**, h1 as **Destination host / worker**, and **Normal ICMP**. Choose **5** samples, **2** events per second and **5** seconds. Click **Start simulation**. Watch the job status, TX/RX counters and forwarding table. The virtual throughput display counts delivered bytes over the last five seconds. Scenario controls generate abstract frames within this application.
5. In **Federated Training → Automatic Retraining Policy**, enable retraining. For a one-reviewed-event experiment set **Verified attack threshold = 1**, **Minimum new eligible samples = 1**, **Minimum participating clients = 2**, one round and one local epoch. Choose the cooldown and deployment policy for your experiment. Keep the validation limits you intend to enforce. Click **Save policy**.
6. On **SDN Network**, choose **Labelled dataset replay**, **Deployed model source**, **Attack**, **Training partition for review**, one sample, and h1 as the mapped destination. Start the simulation. Open the resulting row under **Attack learning history**. Inspect its model version, actual probability, classification, CSV row and inference time. A missed attack is a valid result.
7. Click **Review security event**, inspect the original CSV at the displayed row (line 1 is the header), select the independently confirmed label, enter the evidence, and click **Verify sample**. Use **Reject sample** if the evidence is unsuitable. The scheduler counts distinct eligible records and connected participants. Follow its job in **Federated Training**, **Experiment History**, or the notification bell. A rejected candidate leaves the existing detector active.
8. In **Central Model**, inspect the retrained candidate and compare with its parent. Check the held-out metrics, confusion counts, hashes, sample shares, deployment decision and worker acknowledgements. Open the original virtual frame again for its linked verification, job, contributions and synchronization receipts.
9. To retest, select **Held-out evaluation** under **Labelled dataset replay**. After it runs, open that event, select the two registered versions, and click **Compare held-out sample**. Both predictions use the same original CSV row and compatible preprocessing. The comparison checks holdout membership before inference.
10. Expand **Guided demonstration** on the native SDN page and select your model. Its 24 checkpoints read the actual lineage, jobs, events, reviews and receipts. A rejected candidate, disconnected worker or missing independent review can leave later steps pending. In **Security Monitoring → Security lifecycle log**, filter by organization, worker, version, category, severity or date and export CSV or JSON.

### Observation windows and optional engines

- **Native simulation.** The preset graph supports single-switch, linear, star, tree and custom networks. A custom network starts without links. Use **Inspect node**, **Link peer**, and **Connect** to build a path. Forwarded virtual frames install route entries. Removing links invalidates them. Each completed 13-frame group in a mapped synthetic run supplies 12 measured intervals with four ordered features per interval (bytes, switch hops, interarrival seconds and elapsed seconds).
- **Windows Live Traffic Capture.** Install Npcap using its Windows installer, then run `& web/backend/.venv-tf/Scripts/python.exe -m pip install -r web/backend/requirements-capture.txt`. Choose an authorized interface, duration and optionally a worker for reviewed windows. Click **Start capture**. The passive collector disables promiscuous mode and retains aggregated IP endpoints, protocol and observed byte/packet totals. It retains no packet payloads. Each capture window uses observed bytes, IP protocol number, interarrival seconds and elapsed seconds. For laptop resource use, the collector retains at most one feature window per polling interval. Driver configuration determines who can capture. [Scapy installation](https://scapy.readthedocs.io/en/latest/installation.html)
- **Review and publish.** Under **Review observation windows and publish dataset**, refresh, select each observation, supply an independently supported label and evidence, then **Verify window**. For simulation, generate at least 13 events per run and allow enough time for the selected rate. Publishing requires at least two distinct samples of each class; useful training and validation require substantially more. Train a separate central model on the published CSV. The backend checks the published source and ordered engine-specific feature names before scoring new windows. A 48-column count alone is insufficient. Native and capture features have separate schemas. CSV replay retains the original dataset's feature order, numerical values and scale; arbitrary uploads can lack per-column unit metadata.
- **Linux Mininet.** Select **Linux Mininet** to use the existing authenticated agent and OpenFlow telemetry. The optional installation steps are in **Isolated SDN network** below. When using Windows hosts, skip the Mininet host assignment in the older walkthrough.
- **History and limits.** The virtual graph stores one current network. Removing it retains its database event records. The topology inspector shows the latest 150 events in the current network. Source windows and labelled replays are different evidence. Metadata capture covers traffic visible on the chosen interface and observes in bounded intervals. A synthetic scenario title supplies neither an independently verified training label nor a successful detection.

### Test the Windows implementation

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
& web/backend/.venv-tf/Scripts/python.exe -m pip install -r web/backend/requirements-dev.txt
$env:SECUREFED_RUN_TF_TESTS = '1'
& web/backend/.venv-tf/Scripts/python.exe -m pytest web/backend/tests -q
npm.cmd test --prefix web/frontend
npm.cmd run build --prefix web/frontend
```

For the optional Windows launcher and browser check, install Python Playwright and Google Chrome, set `SECUREFED_NATIVE_BROWSER=1` and run `web/backend/tests/test_native_windows_browser.py` with pytest. It uses temporary data and separate loopback ports. The Windows engine adds SQLite tables for virtual topology, jobs, frames, capture flows, feature windows, published schemas, inspections, comparisons and structured audit records. Existing model artifacts and historical organization assignments stay in their original storage.

For the optional real Npcap check, set `$env:SECUREFED_TEST_NPCAP='1'` and run `& web/backend/.venv-tf/Scripts/python.exe -m pytest web/backend/tests/test_native_network.py -q` from the project root. The test generates its own UDP traffic on a private loopback port. Reviewed capture windows can be published across sessions. The published dataset tracks the worker that supplied each row.

### Verified Windows test results

The November 25, 2026 backend regression run passed 136 tests and skipped four. A separate eight-test run passed the Windows network and federated model lifecycle checks, including passive Npcap capture of test-generated UDP loopback traffic. All 18 frontend tests passed, and the TypeScript production build succeeded.

The isolated backend test followed V0 through V2, verified distinct weight hashes for all three versions, and checked both workers' V2 acknowledgements. In one run, V1 and V2 each scored 80% accuracy and 77.8% F1 on the same 20 held-out records. Use the values from your own run when demonstrating model performance.

Chrome covered Windows startup, virtual network creation, traffic generation, capture-mode navigation and shutdown. The 24 tutorial checkpoints were verified through the backend APIs. The optional Linux Mininet lab was outside this test run.

### Windows implementation file index

| Area | Added | Updated |
| --- | --- | --- |
| Startup and documentation | `start_all.ps1` | `start_backend.ps1`, `start_frontend.ps1`, `stop_services.ps1`, `memory.md` |
| Backend routes under `web/backend/app` | `api/native_network.py` | `main.py`, `api/automation.py`, `api/central.py`, `api/sdn.py` |
| Backend services under `web/backend/app/services` | `native_network.py`, `native_samples.py`, `native_demo.py`, `windows_capture.py`, `security_audit.py` | `automatic.py`, `central.py` |
| Capture dependency | `web/backend/requirements-capture.txt` | |
| Backend tests under `web/backend/tests` | `test_native_network.py`, `test_native_windows_browser.py` | `test_central_models.py`, `test_central_browser.py` |
| React pages under `web/frontend/src/pages` | `WindowsNetwork.tsx` | `SdnPage.tsx`, `SecurityPage.tsx`, `OverviewPage.tsx`, `CentralModelPage.tsx` |
| React components under `web/frontend/src/components` | `SecurityAudit.tsx` | `AutomaticRetraining.tsx`, `ModelAnalysis.tsx` |

## Start here for a ChatGPT-guided demonstration

Attach `memory.md` to ChatGPT and paste the prompt below. Open the [local dashboard](http://127.0.0.1:5173/central-model) on the computer running SecureFed-IDS. If ChatGPT cannot see your browser, share the current screen or read out its status when asked.

> Demonstrate SecureFed-IDS using **Demonstrate verified learning in the browser** above. Select Windows Native Simulation on SDN Network and use the Central Model GUI walkthrough below for additional field details. Start from the page I have open. Guide me one action at a time. Name the sidebar page, give the exact control and value, and tell me what confirms success. If you have access to my local browser, navigate with me and read the displayed results. Otherwise wait for my screenshot or answer before moving on.
>
> Follow one model from V0 through V2. Help me load the labelled CSV, initialize V0, train two organization clients, aggregate their updates into V1, and validate and deploy it. Then map the two workers to virtual hosts, replay one training-partition attack record through a connected client, check the original CSV label with me, and follow the verified event into automatic retraining. Explain that the displayed percentage is the model's attack probability for this record. Report a missed detection if that is what the screen shows.
>
> Keep track of the model name, both client IDs, the event ID, and the parent and candidate versions so we follow the same run across pages. Wait for each job to finish. At the end, show me the V1/V2 weight hashes, evaluation metrics and worker acknowledgements, and explain in plain English what changed. If a gate rejects the candidate, show me the reason and which version is still deployed. Use only values from my run. Ask whether I want to demonstrate rollback after showing the result.

**Before the first click.** On a fresh installation, use the startup commands below. On an existing installation, check **Central Model** for the deployed version and **Federated Training → Automatic Retraining Policy** for the current settings. Record both if you plan to restore them. Deployment switches the active detector for the whole console. For a fresh V0 demonstration on a populated dashboard, use a distinct model name and two unused client names. If you are resuming a demonstration, select the existing model and continue at its first unfinished checkpoint.

## Inspect an existing model in the GUI

For a read-only demonstration, give ChatGPT this prompt:

> Open Central Model and select Campus GRU. Inspect V1 with V0 as the baseline. Show me the held-out record count, the source of V0’s measurements, the change in F1 and false-positive rate, the two client contributions, and the result of verifying each artifact. Read the values from my screen. Finish at the lineage and automatic retraining history. Leave the active model and training policy as you found them.

1. Open **Central Model**, select your model under **Central model**, choose the candidate under **Inspect version**, and choose the baseline under **Compare with**. For Campus GRU, start with **V1** and **V0**. V0 stays labelled initialized. The dashboard can use the first round’s before-training measurements when its recorded parent, weight digests, dataset checksum, held-out row indices, ordered features, scaler and threshold agree.
2. Read **Model performance comparison**. Each card shows baseline, candidate and signed change in percentage points. A change from 60% to 65% is +5 pp. Lower false-positive rate is an improvement. Hover over the grouped bars and change bars. Switch either selector to compare another pair. Under **Model evolution**, toggle metrics and hover over a point for its timestamp. Gaps indicate unavailable or incompatible measurements.
3. Open **Confusion matrix**. For an older version without recorded counts, click **Evaluate V… on holdout**. This runs inference with saved weights and verified preprocessing. Counts and metrics come from the predictions on the fixed holdout. The explicit result stays in the current page session. Missing files or incompatible evidence produce an explanation.
4. In **Model integrity verification**, inspect the weight digest and artifact SHA-256 separately. **View full hash** expands the digest, and **Copy full hash** copies every character. Open **Technical details** for the version ID, parent, creation timestamp, architecture and rounds. Click **Verify artifact** for each version to recompute the file checksum and weight digest. Use the performance measurements to judge whether detection improved.
5. Under **Client contributions**, select a round. The donut shows each aggregated worker’s sample count divided by the round total. Expand a worker for its ID, base version, duration, hash and organization at training. The stacked bars use recorded class counts, or, for older standalone updates, exact sample hashes matched to an independently checksum-verified source CSV. Unrecoverable counts stay unavailable. The current organization comes from the registered client; to correct future rounds use **Federated Clients → Client organization → Save organization**. Historical snapshots retain the original assignment.
6. Click a card in **Model lineage** to inspect that version. Follow the recorded parent even after a rollback. Under **Automatic retraining history**, expand a run to inspect its linked reviewed events, job timing, validation outcome and synchronization receipts. Follow the event into **Security Monitoring** or its experiment into **Experiment History**. Older events can lack a verification timestamp. Deployment and rollback are separate actions at the bottom of the dashboard.
7. To inspect automation settings, open **Federated Training → Automatic Retraining Policy**. Use whole numbers for verified attacks (1–1000), rounds (1–100), epochs (1–50) and cooldown in seconds (0–604800). Enter F1, false-positive rate and allowed F1 decrease as fractions from 0 to 1; minimum accuracy change accepts −1 to 1. For example, 0.95 means 95%. **Save policy** confirms success after reloading the stored values. Leave the policy as found for a comparison-only demonstration.

The optional saved-model Chrome regression uses a private database backup and verifies the original dataset and model file checksums after the test. Build the frontend first. From `web/backend` with Chrome, pytest and Python Playwright available, set `$env:SECUREFED_COMPARISON_MODEL='Campus GRU'` and run `.\.venv-tf\Scripts\python.exe -m pytest tests/test_saved_model_comparison.py -q`.

## Central Model GUI walkthrough

On this Windows installation, open two PowerShell windows. Run the first block in one window and the second block in the other.

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
.\start_backend.ps1
```

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
.\start_frontend.ps1
```

Open [Central Model](http://127.0.0.1:5173/central-model). After updating the project, stop the old development servers with `.\stop_services.ps1` before starting them again. For a new installation, follow [Import and run the complete project](#import-and-run-the-complete-project). For encrypted rounds, install `web/backend/requirements-crypto.txt` in the same Python environment and start the backend with `$env:SECUREFED_ENABLE_CKKS='true'`. For a host-mapped replay, start the configured Mininet lab and confirm its OpenFlow sessions on **SDN Network**.

| Step | GUI action | Evidence |
| --- | --- | --- |
| 1. Prepare data | In **Datasets**, validate and upload `datasets/insdn_compact_1k.csv` as **InSDN** with label column **Label**. | The dataset has 48 ordered numeric features and both classes. |
| 2. Create V0 | In **Central Model → Create Central Model**, enter **Campus GRU**, select that reference dataset and **Random weights**. Under **Model configuration**, use learning rate **0.0001**, batch size **512** and **2** reference training shards. Click **Create V0**. | V0 shows **initialized**, its timestamp, artifact SHA-256 and weight hash. It has zero training rounds. |
| 3. Train two clients | In **Federated Clients → Central model client assignment**, choose **Campus GRU**. Leave **Registered client** on **Create new client**. Enter **Campus A sensor**, organization **Campus A**, select the reference dataset, set **Local epochs** to **1**, check **Train on assignment** and click **Save client assignment**. Repeat with **Campus B sensor** and **Campus B**. If using Mininet, choose one available lab host per worker. | Wait for both local jobs to succeed. The table shows real worker PIDs, eligible benign and attack counts, base V0, elapsed training time and local hashes. Clients assigned the reference CSV receive separate training shards. **Or upload client CSV** accepts a separate schema-compatible local dataset. |
| 4. Configure validation | In **Federated Training → Automatic Retraining Policy**, set the threshold to **1**, rounds and local epochs to **1**, and cooldown to **0** for this tour. Enable retraining and **Deploy after validation**, then **Save policy**. | The policy also supplies the metric gates for manual central rounds. The default allows zero F1 decrease. Keep the validation limits appropriate for the deployment. If a candidate is rejected, inspect the measured regression and retain the previous version. |
| 5. Build V1 | On the same page under **Central federated round**, choose **Campus GRU**, base **V0**, **Aggregate stored local updates**, and both workers. Click **Run selected operation**. | The coordinator weights each update by its eligible sample count. In **Central Model**, inspect V1, including before-and-after metrics on the fixed reference holdout. A rejected candidate stays in version history. |
| 6. Deploy V1 | Select V1 under **Inspect version** and click **Deploy validated version**. | The deployed indicator changes to V1. The synchronization table identifies each acknowledging PID. The experiment and notification bell record the operation. |
| 7. Generate a reviewed event | On **SDN Network**, select the mapped **Lab host**, check **Replay training partition for independent review**, then click **Replay labeled attack**. Alternatively, on **Security Monitoring**, select the client and click **Score training-partition attack sample**. Open the event under **Security event history**. Open the original CSV with the header on line 1, find the displayed CSV row, and check its **Label** column (1 = Attack, 0 = Benign). If it is 1, select **Attack** under **Reviewed label**, enter your source under **Independent label evidence**, then click **Verify sample**. | The event shows the organization, client, origin, model version and actual prediction. A replay can produce a missed detection. Ordinary held-out attack replays remain evaluation-only. |
| 8. Inspect V2 | Follow the automatic run in **Federated Training** or **Experiment History**. Return to **Central Model**, select V2 and choose V1 under **Compare with**. | Compare weight hashes, accuracy, precision, recall, F1 and false-positive rate. A passing candidate deploys when the policy permits. The contribution and acknowledgement tables show who trained and who actually loaded the version. |
| 9. Restore a version | Select previously deployed V1 and click **Roll back to version**. Use **Synchronize workers** to check connected participants immediately. | The active version returns to V1 and the bell records the rollback. Missing acknowledgements are retried when a participant reconnects. |

**Other initialization methods.** **Restore registered global model** starts a new lineage from a registered artifact. **Import pretrained artifacts** accepts a SecureFed GRU weight JSON and its matching `preprocessing.json`. For trained versions these files are under `web/var/models/<experiment-id>/<version-id>/`. Pick the matching reference CSV. The import checks the weight layout, source checksum, feature order, clean split and scaler. All three methods create a V0 baseline that requires a validated training round before deployment.

**Lab limits.** The coordinator has one active inference model across all named lineages. Training uses local worker subprocesses and the configured dataset row cap (default 5,000). The clean reference split uses seed 42 and a 30% holdout by default. Set **Split seed** and **Holdout fraction** to match the preprocessing sidecar when importing an existing model. Duplicate feature vectors count once per worker, and overlapping client contributions are rejected. Independent single-client jobs store plaintext updates. For encrypted aggregation, select **Train fresh and aggregate → Require CKKS encryption**, or **Require CKKS** on the automatic policy. That round creates a common ephemeral key for all participants. A CKKS failure stops the run. Mininet counter windows require their own compatible feature schema; the CSV replay and live capture are distinguishable in event history. These local experiments measure behavior on the chosen dataset.

**Reproduce the tests.** From the project root, run the following using the project Python environment. The opt-in integration tests take several minutes, use temporary model stores and train real workers.

```powershell
$env:SECUREFED_RUN_TF_TESTS='1'
Push-Location web/backend
.\.venv-tf\Scripts\python.exe -m pytest tests -q
Pop-Location
npm.cmd test --prefix web/frontend
npm.cmd run build --prefix web/frontend
```

For the Chrome GUI test, keep the frontend on port 5173 and the authenticated Mininet lab running with hosts h1 and h2. From the project root run the following. The test starts its own temporary API, database and headless browser profile. If using the root virtual environment, substitute its Python executable for `web/backend/.venv-tf/Scripts/python.exe`.

```powershell
$env:SECUREFED_BROWSER_TEST='1'
$env:SECUREFED_LAB_TOKEN=(Import-Clixml -LiteralPath '.\web\var\sdn-agent.credential.xml').GetNetworkCredential().Password
.\web\backend\.venv-tf\Scripts\python.exe -m pip install playwright
.\web\backend\.venv-tf\Scripts\python.exe -m pytest web/backend/tests/test_central_browser.py -q
```

### Finish the demonstration

In **Experiment History**, open the automatic experiment and follow its triggering event ID back to **Security Monitoring**. Match the client, organization and scoring version to the replay. In **Central Model**, open the candidate and compare it with its parent. Use the notification bell to trace verification, validation, deployment and synchronization.

| What to read aloud | Where to find it |
| --- | --- |
| Which client saw which sample? | **Security Monitoring → Security event history** shows the event ID, client, organization, origin, CSV row, prediction, probability and verified label. |
| Did the model change, and did detection improve? | **Central Model → Inspect version → Compare with** shows the weight hashes and metrics. Report the held-out row count and before/after F1 and false-positive rate. A changed hash alone establishes a weight update. |
| Which version is serving, and who received it? | Read **Deployed** on Central Model. Match the version to the acknowledgement table and read each client ID and worker PID. A contribution records training; an acknowledgement confirms the worker loaded the version. |

If no automatic job appears, check the event origin first. A held-out replay stays evaluation-only. For a training-partition event, check the independent **Attack** label, worker connections, saved threshold and cooldown. For a failed job, open its recorded error. For a rejected candidate, keep the observed result in the demonstration and explain the failed gate. Restore any temporary policy settings when finished. Rollback in step 9 is optional.

## Alternative GUI walkthrough for a manual experiment

Use this path when demonstrating a manually created experiment. For the named V0 → V1 → V2 demonstration, follow the Central Model walkthrough above.

| Step | What to do in the GUI | How to tell it worked |
| --- | --- | --- |
| 1. Choose the data | Open **Datasets**. Reuse the validated `insdn_sdn_ids_5k` dataset. If it is missing, select `datasets/insdn_sdn_ids_5k.csv`, choose **InSDN**, then **Validate** and **Upload**. | The dataset appears in the list with 5,000 rows and 48 input features. |
| 2. Connect two clients | In **Federated Clients**, reuse two connected workers. To create one, enter a **Client name**, click **Create client**, then **Enable** in its row. Repeat for the second worker. | Each row shows **Connected** and its own process ID (PID). |
| 3. Train the global model | In **Federated Training**, name an experiment, select the dataset and **2 clients**, and click **Create experiment**. In the experiment detail, check both workers, choose **Verification (3 rounds, 1 local epoch)**, then **Train Global Model**. Leave **Initialize from admitted global model** unchecked for a fresh run. | The job progresses through three rounds and shows **Succeeded**. If the workers are missing, click **Refresh clients**. |
| 4. Check what changed | In **Performance Evaluation**, choose your run under **Completed experiment**. Expand a round to see each client’s sample count, loss and update hash. | The global hashes show whether the weights changed. The before-and-after accuracy and F1 scores on the same held-out rows show whether detection improved. |
| 5. Deploy and check participation | Return to your experiment in **Federated Training** and click **Deploy Global Model**. Open **Intrusion Detection**, then **Overview → Client connections to the central model**. | Intrusion Detection shows **Inference available** and the active version. Overview identifies the workers that **Contributed**. |
| 6. Test detection through one client | Open **Security Monitoring**, choose one connected **Federated client**, and click **Replay attack sample**. | Read **Attack detected** or **Attack missed**, the attack probability, CSV row, and model version. **Transmission confirmed** identifies the worker PID and the 48 features sent for scoring. |

The replay uses a held-out row already labeled **Attack**. Its percentage is the model’s score for that one row. Replaying it performs inference only. To check a benign example, open **Intrusion Detection → Labeled dataset samples**, choose **Held-out prediction** and **Benign**, then **Load sample → Request sample prediction**.

**Optional SDN lab:** To inspect actual network traffic, open **SDN Network**, confirm the controller is connected, select a mapped host, and click **Send normal ping**. The [SDN dashboard walkthrough](#dashboard-walkthrough) covers topology setup, traffic capture, label review and retraining.

## Demonstrate automatic retraining in the GUI

Use the first five steps of the walkthrough above to deploy a clean GRU and connect at least two registered workers. A previously deployed clean model works if its original CSV and preprocessing artifacts are still available. The two-client demonstration works with the bundled labelled dataset on Windows. The optional Mininet path uses the Ubuntu agent described below.

1. Open **Federated Clients → Client organization**. Select each worker by ID, enter its organization and click **Save organization**. On **SDN Network**, existing host mappings show the organization, worker ID and host IP. For a host-specific demonstration, select a mapped host there.
2. Open **Federated Training → Automatic Retraining Policy**. Check **Enable automatic retraining**. For a one-event demonstration, set **Verified attack threshold** to **1**, **Rounds** to **1** and **Local epochs** to **1**. Choose the minimum candidate F1, minimum accuracy change, maximum false-positive rate and allowed F1 decrease. These use fractions, so 0.02 means two percentage points. Check **Deploy after validation** to exercise automatic deployment, then click **Save policy**. A fresh installation starts with automatic retraining and deployment disabled, a threshold of three and a five-minute cooldown.
3. In **Security Monitoring**, select a connected client and click **Score training-partition attack sample** under **Security event history**. For a mapped host, use **SDN Network**, check **Replay training partition for independent review** and replay a labelled sample there instead. Open the resulting event in **Security Monitoring**. Read its origin, model version, CSV row, prediction and attack probability. The bundled CSV is synthetic. Replay sends a labelled record through the worker for inference. Live packet capture is a separate operation.
4. Open the source CSV and check the displayed row against its label column. In the event, select the **Reviewed label**, enter the evidence you used under **Independent label evidence**, and click **Verify sample**. An example is the dataset filename, row number and its recorded label. Only verified attacks with compatible features and eligible provenance can trigger training. A verified attack may have been missed by the detector. Ordinary **Replay attack sample** uses held-out data and remains evaluation-only after review.
5. Return to **Federated Training → Automatic Retraining Policy**. Expand the run to see its triggering event IDs, worker IDs, job progress, parent and candidate. The workers start with the deployed weights and train on assigned shards containing existing labelled training data. A reviewed CSV row is assigned once to the reviewing worker. Compatible independently labelled live windows can be added to training. The original test indices and scaler are preserved.
6. In **Experiment History**, open the automatic experiment. Compare the two global weight hashes and the accuracy, precision, recall, F1 and false-positive rate on the same held-out rows. A **rejected** run preserves the active version. A **validated** run passed and is staged. A **deployed** run passed and activated the new version. Check the active version in **Intrusion Detection**. Under the automatic run, each synchronization acknowledgement identifies the actual worker PID and version. A disconnected worker can acknowledge after reconnecting.
7. Open the notification bell in the header. Its unread count and messages persist across refreshes. Follow an event link from the run to inspect the originating sample. Use **Intrusion Detection → Restore selected version** to roll back. After a failed job, correct the reported issue, then use **Retry failed run**. Disable the automatic policy and click **Save policy** when the demonstration is finished.

**Using CKKS.** Install the project's TenSEAL dependency and enable the backend's CKKS capability, then select **Require CKKS** in the policy. Registered workers encrypt their local updates. The aggregation backend combines ciphertexts and the existing keyring decrypts the aggregate. Key management and workers run on the same lab computer. An unavailable encryption backend fails the job. The plaintext option must be selected explicitly for a subsequent plaintext run.

**Reading event history.** An alert is a positive prediction. A high-severity alert has an attack probability of at least 90%. A verified label records the operator's independent evidence. Source and destination IPs are populated when observed during capture. Live counter windows use the agent's own feature order and can be scored only by a compatible deployed GRU. Manual scores have no independent sample provenance and are ineligible. The dashboard polls the API every five seconds. SQLite retains events, policy, notifications, run reservations and worker acknowledgements across backend restarts.

## Import and run the complete project

**To reproduce this working copy on another computer**, copy the project root with its current source files, both launcher scripts, the frontend lockfile and the `datasets/` folder. Local edits and newly created files travel with a filesystem copy. A Git clone contains the version committed and pushed to the remote. For a source-only install, recreate the Python environment and Node dependencies on the destination. To migrate existing jobs, uploads and trained models too, stop the backend before copying the entire `web/var/` directory.

For the published repository, use the following commands. If you already have a copy, open PowerShell in the directory containing `memory.md` and skip the clone.

```powershell
git clone https://github.com/hari10621/SECURE-FEDERATED-IDS.git SecureFed-IDS
cd SecureFed-IDS
```

Use Python 3.12 on Windows and a Node.js version supported by the locked Vite package (Node 20.19+ within the 20.x line, or 22.12+). Install from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r web/backend/requirements-training.txt -r web/backend/requirements-dev.txt
npm.cmd ci --prefix web/frontend
```

Run `.\start_backend.ps1` in the activated terminal. In a second PowerShell window at the repository root, run `.\start_frontend.ps1`. The backend launcher enables GRU training and predictions, enables the CKKS capability check unless SECUREFED_ENABLE_CKKS is explicitly false, and uses the activated Python environment when available. Otherwise it looks for the project environments in `.venv` and `web/backend/.venv-tf` before using Python on PATH. Both launchers recognize an already-running local service. The frontend launcher starts Vite. Open the [dashboard](http://127.0.0.1:5173/). Check [API health](http://127.0.0.1:8000/api/v1/health) and the [interactive API reference](http://127.0.0.1:8000/docs) independently.

## Train and use your own model

1. On **Datasets**, select the validated **insdn_sdn_ids_5k** dataset or upload `datasets/insdn_sdn_ids_5k.csv`. Use 48 numeric features in training order and a binary label. An optional `attack_type` column supplies descriptive metadata. The bundled CSVs are synthetic research fixtures with binary labels.
2. On **Federated Clients**, create four uniquely named clients. Enable each and wait for its connected status and process ID. On Windows the PID identifies the worker handling requests. Disabling a client stops its worker.
3. On **Federated Training**, create an experiment using the dataset and a client count of four. Select the four connected workers. Choose **Verification (3 rounds, 1 local epoch)** and **Train Global Model**. The plaintext run uses batch 512, learning rate 0.0001, sample weighting, seed 42 and a 30% held-out split. Training fits the scaler on the training partition. A clean first run starts with new weights. For a subsequent experiment, **Initialize from admitted global model** requires the same data, clean split, schema and scaler.
4. Open the experiment in **Federated Training**, **Experiment History** or **Performance Evaluation**. Expand a round to see the client IDs, sample counts, losses, update hashes and before/after global hashes. Compare the initial and final metrics on the same held-out records. A weight change alone does not establish better detection.
5. In the successful experiment detail, click **Deploy Global Model**. Open **Intrusion Detection** and check the active version, SHA-256, source experiment, feature order and label mapping. **Reload Model** reopens and validates the saved artifacts. To roll back, pick a previously validated version and click **Restore selected version**.
6. Under **Labeled dataset samples**, choose the active model’s source dataset, **Held-out prediction**, and **Attack** or **Benign**. Click **Load sample**, then **Request sample prediction**. Compare actual label, prediction and confidence. If the dataset includes attack types, the first load populates the selector. Raw manual predictions accept exactly 48 finite numbers in the displayed order.
7. To assign a training row, select **Train · [client name]** under **Sample use**, choose the category, load a sample and assign it. Select that same registered client in the next experiment. The backend checks assignments against the actual training split. Held-out evaluation uses the deployed model’s saved test indices.

### Restart on Windows

Stop foreground launchers with Ctrl+C in each service terminal. For background services started from this checkout, run the commands below after training finishes. The script checks the project path and process command line before stopping each listener.

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
.\stop_services.ps1
```

Start the services in two separate PowerShell windows. An already-running launcher reports its URL and leaves that process running.

Backend, using the TensorFlow environment in this checkout:

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
. .\web\backend\.venv-tf\Scripts\Activate.ps1
$env:SECUREFED_ENABLE_CKKS = 'true'
.\start_backend.ps1
```

Frontend:

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
.\start_frontend.ps1
```

Open [the dashboard](http://127.0.0.1:5173/) and [prediction status](http://127.0.0.1:8000/api/v1/predictions/status). The launcher sets the backend working directory. At an interactive PowerShell prompt, use the project path above because `$PSScriptRoot` is only populated inside a script. The CKKS capability check needs TenSEAL in the backend environment. Plaintext experiments work independently.

### Execution modes

| Mode | Purpose |
| --- | --- |
| Plaintext federated GRU | Train local client workers, aggregate updates and evaluate each round. This is the primary demo. |
| Reference simulation | Exercise partitioning, aggregation and metrics using a lightweight linear backend. Enable with `SECUREFED_ENABLE_SIMULATION`. |
| Centralized GRU | Select `mode: "centralized"` on a training request to train on pooled training rows as a baseline. |
| Paper comparison suite | Compare a centralized baseline with in-process federated runs at 4, 8 and 12 clients. Defaults are 15 rounds, five local epochs and batch size 512. The suite defaults to plaintext. |
| Optional encryption and legacy research | Separate CKKS implementations and adapters are present for research use. The plaintext demo requires neither TenSEAL nor an external research checkout. |

## Repository map

| Location | Contents |
| --- | --- |
| [datasets](datasets/) | Three bundled synthetic CSVs, their generator and schema guide. Large local CICIDS2017 CSVs under `web/backend/` are ignored by Git. |
| [Backend entry point](web/backend/app/main.py) | FastAPI startup, service registration, job handlers, CORS and route registration. |
| [Backend API](web/backend/app/api/) | Health, clients, datasets, experiments, jobs, metrics, predictions and IPS endpoints. |
| [Domain code](web/backend/app/domain/) | CSV loading, preprocessing, GRU weight serialization and evaluation metrics. [Federated training](web/backend/app/domain/federated/) contains the round loop, process worker and aggregation server. [Crypto](web/backend/app/domain/crypto/) contains optional backends. |
| [Services](web/backend/app/services/) | Dataset validation, client records, experiment orchestration, job management, training, inference, SDN integration and the [client tutorial](web/backend/app/services/client_tutorial.py). |
| [Configuration](web/backend/app/config.py), [database models](web/backend/app/models.py), [schemas](web/backend/app/schemas.py), [storage](web/backend/app/storage/) | Runtime settings, persisted records, request/response contracts and artifact locations. |
| [Research scripts](web/backend/research/) | Dataset-specific historical experiments, figure generation and SHAP analysis. These are separate from the web app entry point. |
| [Frontend](web/frontend/) | React, TypeScript, Vite and Tailwind. [Pages](web/frontend/src/pages/) implement the console screens. [Components](web/frontend/src/components/) include the tutorial and charts. [API client](web/frontend/src/lib/api.ts) connects them to FastAPI. |
| [Backend tests](web/backend/tests/) and [frontend sources](web/frontend/src/) | Pytest API/domain/integration tests and colocated Vitest tests. |
| Root scripts | The two launchers start the app. The `check_*`, `demo_*`, `run_*` and `frontend_*` helpers support diagnostics and development. Some older helpers use machine-specific paths. Use the portable commands below for verification. |

## Dashboard and API

All API paths below are relative to `http://127.0.0.1:8000/api/v1`. The [OpenAPI schema](http://127.0.0.1:8000/openapi.json) lists request fields, response types and all supported operations.

| Dashboard area | API entry points |
| --- | --- |
| Overview and tutorial | `GET /health`, `GET /version`, `POST /jobs/client-tutorial`, `GET /jobs/client-tutorial/latest` |
| Datasets | `POST /datasets/validate`, `POST /datasets` (multipart upload), `GET /datasets`, `POST /datasets/{id}/validate` |
| Federated Clients | `GET` or `POST /clients`, `PATCH /clients/{id}`, `POST /clients/{id}/enable` or `/disable`, `GET /clients/{id}/status` |
| Training, history and performance | `POST /experiments`, `POST /experiments/{id}/train` or `/simulate`, `GET /experiments/{id}`, `GET /experiments/{id}/metrics`, `POST /experiments/run-paper-suite` |
| Job progress and cancellation | `GET /jobs/{id}`, `POST /jobs/{id}/cancel` |
| Intrusion Detection | `GET /predictions/status`, `POST /predictions` with a JSON `features` array |
| Security Monitoring | `POST /clients/{client_id}/attack-replay` scores a recorded attack through a connected worker. `GET /sdn/inventory/events` supplies SDN lab detections. |
| SDN Network | `GET /sdn/status` and `GET /sdn/topology` report controller sessions, hosts, switches and links. |
| Settings | Configure the browser's API base URL and optional bearer token. |

The API also exposes `GET /encryption/status` for capability checks, `POST /ips/detect` for inference and `POST /ips/mitigate` for read-only recommendations.

## Configuration and persisted data

Set environment variables in the backend shell before startup. A direct Uvicorn launch uses the defaults in [config.py](web/backend/app/config.py). The [Windows launcher](start_backend.ps1) enables training and predictions. The CKKS capability flag is independent of plaintext training.

| Setting | Default or effect |
| --- | --- |
| `SECUREFED_BASE_DIR`, `SECUREFED_DATA_DIR` | Default to `web/` and `web/var/`. The data directory must be under the configured base. |
| `SECUREFED_DATABASE_URL` | Defaults to SQLite at `web/var/securefed.db`. It stores client records, dataset metadata, experiments and job results. |
| `SECUREFED_MAX_UPLOAD_BYTES`, `SECUREFED_MAX_CSV_ROWS` | 512 MiB and 2,000,000 rows by default. The separate training cap controls how many rows are used in an experiment. |
| `SECUREFED_TRAINING_MAX_ROWS`, `SECUREFED_SIMULATION_MAX_ROWS` | 5,000 and 50,000 rows respectively. |
| `SECUREFED_JOB_WORKERS` | One background worker by default. |
| `SECUREFED_API_TOKEN` | Optional bearer token for protected API routes. |
| `SECUREFED_ENABLE_RESEARCH_EXECUTION`, `SECUREFED_RESEARCH_REPO_DIR` | Gate and locate the external legacy research checkout. |

Uploaded CSVs are stored in `web/var/datasets/`. Experiment training writes JSON weights, preprocessing and result artifacts beneath `web/var/models/<experiment-id>/<run-id>/`. The active prediction manifest is `web/var/models/manifest.json`. Tutorial results are stored with their job. Copying only the SQLite database omits uploaded data and model artifacts.

## Verify an installation

From the repository root, with the Python environment active:

```powershell
Push-Location web/backend
python -m pytest tests -q
Pop-Location
npm.cmd --prefix web/frontend test
npm.cmd --prefix web/frontend run build
```

To exercise the real TensorFlow upload-to-prediction test explicitly:

```powershell
Push-Location web/backend
$env:SECUREFED_RUN_TF_TESTS = '1'
python -m pytest tests/test_training_api.py::test_real_keras_gru_training_completes -q
Pop-Location
```

| Symptom | What to check |
| --- | --- |
| Dashboard cannot reach the API | Open the health endpoint. Check the backend terminal and the base URL in Settings. |
| Training disabled or TensorFlow unavailable | Activate the environment used to install the training requirements, then start the backend with the supplied launcher. |
| Dataset uploads but cannot train | Check that it has 48 numeric features, a final binary label column and a valid schema report. |
| Predictions unavailable after the tutorial | Train a regular plaintext GRU experiment with predictions enabled. The tutorial keeps its model separate. |
| Tutorial route returns 404 | Restart the backend from the same project copy as the frontend so both serve the tutorial version. |

## Isolated SDN network

The Windows FastAPI service talks to a bearer-authenticated Ubuntu Mininet agent over loopback. For a separate VM, forward the agent port over SSH. Inside Ubuntu the OVS learning controller listens on 127.0.0.1:16653, the agent on 127.0.0.1:8765, and switches negotiate OpenFlow 1.3. Hosts have private veth links in network namespaces. The agent creates only its own switches and links and provides fixed operations for lifecycle, inventory, two ICMP echoes and short host captures. There is no shell-command API, external traffic target, NAT or physical interface attachment.

### Ubuntu setup

Use a dedicated Ubuntu VM with Mininet/OVS kernel support. From a copy of the project root inside the VM:

```bash
sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch openvswitch-testcontroller iproute2 iputils-ping openssl
sudo systemctl start openvswitch-switch
sudo install -d -m 700 /opt/securefed-lab
sudo install -m 700 lab/start.sh lab/mininet_agent.py lab/capture_window.py /opt/securefed-lab/
sudo sh /opt/securefed-lab/start.sh
```

Keep that terminal running. Stop the network from the GUI before shutting down the agent. The configuration and counter history last for the agent session. Sample reviews, event receipts and mappings are stored in Windows at `web/var/sdn.sqlite3`, scoped to the lab identifier. Deleted configurations get a new ID when recreated. The agent credential is private to root at `/run/securefed-sdn/token` and renews after VM reboot. The controller endpoint and OpenFlow port in the form refer to Ubuntu loopback. A different OpenFlow 1.3 controller can run there when configured separately. The stock startup script launches the OVS learning controller.

### Windows connection

On this computer the Ubuntu WSL2 distribution supplies the VM and Windows localhost forwarding supplies the tunnel. To start the previously installed agent again:

```powershell
wsl.exe -d Ubuntu -u root -- sh /opt/securefed-lab/start.sh
```

In a second PowerShell terminal, start the backend from the repository root:

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
$env:SECUREFED_LAB_TOKEN = (wsl.exe -d Ubuntu -u root -- cat /run/securefed-sdn/token).Trim()
$env:SECUREFED_LAB_PORT = '8765'
$env:SECUREFED_LAB_TIMEOUT = '20'
.\start_backend.ps1
```

For a separate Ubuntu VM, replace the WSL credential command with the token from that VM (read it using sudo in the VM terminal). Use a host-only management interface and an SSH account with a verified host key. Start the tunnel in its own Windows terminal, replacing the example account and address:

```powershell
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 ubuntu@192.168.56.101
```

In the backend terminal, enter the VM token privately:

```powershell
$credential = Get-Credential -UserName 'sdn-agent' -Message 'Enter the Ubuntu agent token as the password'
$env:SECUREFED_LAB_TOKEN = $credential.GetNetworkCredential().Password
.\start_backend.ps1
```

The launcher also supports a Windows user-encrypted credential at `web/var/sdn-agent.credential.xml`. An explicit environment variable takes precedence. Restart the backend after changing agent credentials. In another Windows terminal:

```powershell
Set-Location 'C:\Users\HARIS\Desktop\SecureFed-IDS'
.\start_frontend.ps1
```

### Dashboard walkthrough

1. Open **SDN Network**. Choose single, linear or tree, switch count, total host count, private subnet and controller endpoint. **Create network** saves the configuration; **Start network** constructs it in Ubuntu. The default linear network connects two switches, four client hosts and one testing host. **Refresh topology** checks actual switch controller sessions. A running network refreshes every five seconds. **Stop network** tears down its links; **Delete network** clears the stopped configuration.
2. Zoom, pan and select a node. Inspect host IP/MAC, switch port, TX/RX counters and worker mapping. Expand a switch for its OpenFlow rules. Packet totals and rates use host egress to avoid counting forwarded packets repeatedly at every switch. Throughput is based on differences in bytes and elapsed monotonic time. The default veth links have no configured bandwidth ceiling, so utilization percentage is unavailable.
3. Under **Host testing and reviewed samples**, choose a host and a registered worker, then **Map client**. The worker PID is measured on Windows. The deployed participation column comes from the model manifest. A mapped host has no independently reported local model version. Remote training would require a host-side agent, mutual authentication, a challenge-bound round/model hash, shard authorization and verified update receipts. The current Ubuntu agent owns capture and network operations only.
4. Select **Send normal ping**. The last lab host sends two ICMP requests to the selected host. To see protocol counts and endpoint pairs, check **Include normal ICMP during capture**, then **Capture host window**. This records up to 100 observed IPv4 flows, including TCP/UDP ports when present during the sampling window. Packet headers stay in the VM; only metadata and measured rates cross the management link.
5. **Replay labeled attack** passes a held-out source CSV row through the mapped Windows worker and scores it with the admitted GRU. It produces a recorded replay event, without injecting attack packets. **Security Monitoring → SDN lab detections** displays source, host, score and model version. Topology alert indicators include both live detections and recorded replays. Ordinary forwarding rules are visible in the inventory. IPS offers review advice only.
6. To train on live measurements, review a counter window under its mapped host and approve its independently known label. Each row is 12 consecutive approximately 250 ms intervals, each containing TX packets/s, RX packets/s, TX bytes/s and RX bytes/s in that order. Rates use the actual elapsed time. Names run from `interval_01_tx_packets_per_second` to `interval_12_rx_bytes_per_second`. The legacy research CSV contains normalized protocol values, application metadata and generated anomaly scores whose semantics cannot be recovered from switch counters. Live scoring requires an exact ordered counter-schema match.
7. Once both classes have reviewed samples sufficient for training and holdout, **Publish reviewed dataset**. In **Federated Training**, select that dataset and all its contributing workers, then train in clean plaintext mode. The original capture owner determines training shards. The held-out split precedes scaler fitting and assignment. Inspect round metrics, validate, then choose **Deploy Global Model**. A subsequent capture with this schema produces a live prediction. Until such a model is deployed, the GUI displays the measurement and its review status. A model prediction never supplies the approval label.

The read API includes `GET /api/v1/sdn/status`, `/sdn/topology` and `/sdn/inventory/{hosts,switches,links,flows,history,events}` under the same prefix. The interactive API reference lists lifecycle, mapping, capture, replay and review routes. The VM agent uses Mininet's switch connection status and reads actual flow tables using `ovs-ofctl -O OpenFlow13 dump-flows`. [Mininet switch API](https://mininet.org/api/classmininet_1_1node_1_1OVSSwitch.html) · [Open vSwitch OpenFlow reference](https://docs.openvswitch.org/en/latest/faq/openflow/)

Run the real VM integration test from the repository root with `sudo /usr/bin/python3 lab/test_mininet.py`. It creates temporary single, linear and tree networks, checks controller loss, captures actual ICMP, and removes its own networks.
