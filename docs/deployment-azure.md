# Azure deployment runbook

How BroccoliDetect gets onto Azure, step by step. The deployment unit is the
**single combined container** built by [`Dockerfile.azure`](../Dockerfile.azure)
(nginx serving the React UI + proxying to a loopback uvicorn) — one container
app, one model, per the course rules. CI builds and pushes the image; the last
hop onto the platform is a documented manual command (the course tenant does
not grant service principals with resource-group rights).

The app runs on **Azure App Service (Web App for Containers)**. We originally
targeted Azure Container Apps, but at rollout time environment creation in
westeurope was refused with `AKSCapacityHeavyUsage` — a regional capacity
outage on the AKS infrastructure that backs Container Apps. Because the
deployment artifact is a self-contained image, the identical container
deploys to App Service (the other course-approved service, same region)
with zero changes; §3 documents both paths.

Everything here uses the `az` CLI on macOS/Linux (bash/zsh). All names follow
the `teamXX-service-name` convention and live in the team's assigned resource
group in `westeurope` — both course rules.

---

## 0. Prerequisites

- Azure CLI (`brew install azure-cli`), logged in: `az login`
- Docker Desktop running
- Your team's assigned resource group name (referred to as `$RG` below)

```bash
export RG=<your-team-resource-group>      # assigned by the course - do not create one
```

Copy the Makefile's Azure settings file and fill in `RESOURCE_GROUP`:

```bash
cp deploy/azure/azure.env.example deploy/azure/azure.env
# edit deploy/azure/azure.env -> RESOURCE_GROUP=<your-team-resource-group>
```

`deploy/azure/azure.env` is git-ignored; the Makefile picks it up automatically.

## 1. One-time: Container Registry

```bash
az acr create --resource-group "$RG" --name teamb4broccoliacr --sku Basic
az acr update --name teamb4broccoliacr --admin-enabled true
az acr credential show --name teamb4broccoliacr   # note username + password
```

## 2. One-time: GitHub repository secrets (enables CI/CD)

In the GitHub repo: Settings → Secrets and variables → Actions → New repository
secret. Create exactly these three (the deploy workflow reads them):

| Secret | Value |
| --- | --- |
| `ACR_LOGIN_SERVER` | `teamb4broccoliacr.azurecr.io` |
| `ACR_USERNAME` | username from `az acr credential show` |
| `ACR_PASSWORD` | password from `az acr credential show` |

From then on, every push to `main` runs **"B4 BroccoliDetect - Build & Push to
ACR"**: backend pytest + frontend Vitest first, and only if both pass does the
image get built and pushed as `:latest` and `:sha-<commit>`. (The plain CI
workflow runs on every push/PR and never touches the registry.)

First image without waiting for CI (optional):

```bash
make build acr-login push
```

## 3. One-time: create the app

Shared notes for both platforms:

- The container listens on **port 80** (nginx inside the combined image).
- **`API_KEY`** is stored as a platform secret/app setting, never in the
  repo. Inside the container, nginx injects it on proxied `/api/` calls, and
  uvicorn (loopback-only) enforces it — so the public URL serves the UI while
  the API itself is key-protected. Keep the key alphanumeric
  (`openssl rand -hex 32`): it is substituted into the nginx config, where
  quotes or semicolons would break the rendered file.
- **`DEPLOY_ENV=production`** hides `/docs` and makes the weights integrity
  check mandatory (the hash comes from `backend/weights/registry.json`;
  set `EXPECTED_WEIGHTS_SHA256` explicitly only to override it).

### Option A — App Service (the deployed platform)

```bash
az appservice plan create --name teamb4-broccoli-plan --resource-group "$RG" \
  --location westeurope --is-linux --sku B1

az webapp create --name teamb4-broccoli-api --resource-group "$RG" \
  --plan teamb4-broccoli-plan \
  --container-image-name teamb4broccoliacr.azurecr.io/broccoli-detect:latest

az webapp config container set --name teamb4-broccoli-api --resource-group "$RG" \
  --container-image-name teamb4broccoliacr.azurecr.io/broccoli-detect:latest \
  --container-registry-url https://teamb4broccoliacr.azurecr.io \
  --container-registry-user teamb4broccoliacr \
  --container-registry-password "$(az acr credential show --name teamb4broccoliacr --query 'passwords[0].value' -o tsv)"

az webapp config appsettings set --name teamb4-broccoli-api --resource-group "$RG" --settings \
  WEBSITES_PORT=80 API_KEY=$(openssl rand -hex 32) DEPLOY_ENV=production MODEL_VERSION=v1.0.0

az webapp log config --name teamb4-broccoli-api --resource-group "$RG" \
  --docker-container-logging filesystem
az webapp restart --name teamb4-broccoli-api --resource-group "$RG"
```

URL: `https://teamb4-broccoli-api.azurewebsites.net`. The **first** start
pulls the ~2 GB image and loads the model — allow 3–5 minutes. B1 (1.75 GB
RAM, 1 core) is the smallest tier that fits torch comfortably. Live logs:
`az webapp log tail --name teamb4-broccoli-api --resource-group "$RG"`.

### Option B — Container Apps (alternative; capacity-dependent)

At rollout time this failed with `AKSCapacityHeavyUsage` in westeurope; the
commands are kept for when regional capacity returns. After any "failed"
create, check `az containerapp env show … --query properties.provisioningState`
before reacting — the CLI sometimes reports failure while the resource lands.

```bash
az containerapp env create --name teamb4-broccoli-env \
  --resource-group "$RG" --location westeurope

az containerapp create --name teamb4-broccoli-api \
  --resource-group "$RG" \
  --environment teamb4-broccoli-env \
  --image teamb4broccoliacr.azurecr.io/broccoli-detect:latest \
  --registry-server teamb4broccoliacr.azurecr.io \
  --target-port 80 --ingress external \
  --secrets api-key=$(openssl rand -hex 32) \
  --env-vars API_KEY=secretref:api-key DEPLOY_ENV=production MODEL_VERSION=v1.0.0
```

Resources: defaults (0.5 vCPU / 1 Gi) per the course's small-settings rule;
raise to `--cpu 1 --memory 2Gi` only if the app is OOM-killed at startup.

## 4. Releasing a new version (the lifecycle loop)

1. Merge / push to `main` → the deploy workflow tests, builds, and pushes
   `:sha-<commit>` to ACR. The run summary shows the redeploy step.
2. Point the app at it (the one manual step):

```bash
make deploy TAG=sha-<commit>      # = az webapp config container set + restart
```

   (`TAG=latest` deploys the newest CI build; on Container Apps the
   equivalent is `make deploy-containerapp TAG=…`.)

3. Verify: open `https://<public-url>/api/metadata` — `app.git_sha` must equal
   the commit you deployed, `model.version`/`model.verified` describe the
   loaded weights. **Rollback** is the same command with an older `sha-` tag.

## 5. Model weights in Blob Storage (update a model without rebuilding)

The current model (`v1.0.0`) ships inside the image, so nothing is required
for the app to run. Blob storage is how a **new** model version rolls out
without an image rebuild.

```bash
# One-time: storage account + containers
az storage account create --name teamb4broccolist --resource-group "$RG" \
  --location westeurope --sku Standard_LRS
KEY=$(az storage account keys list --account-name teamb4broccolist \
  --resource-group "$RG" --query '[0].value' -o tsv)
az storage container create --name models   --account-name teamb4broccolist --account-key "$KEY"
az storage container create --name datasets --account-name teamb4broccolist --account-key "$KEY"

# Upload the weights under their version tag
az storage blob upload --account-name teamb4broccolist --account-key "$KEY" \
  --container-name models --name model-v1.0.0.pt --file backend/weights/best.pt

# Read-only SAS URL (set a sane expiry; the URL is a credential - treat it like one)
az storage blob generate-sas --account-name teamb4broccolist --account-key "$KEY" \
  --container-name models --name model-v1.0.0.pt \
  --permissions r --expiry 2026-09-01 --https-only --full-uri -o tsv
```

To roll out a (re)trained model `v1.1.0`:

1. Add its entry (file `model-v1.1.0.pt`, sha256, dataset version, metrics) to
   `backend/weights/registry.json` and merge — never edit released entries.
2. Upload `model-v1.1.0.pt` to the `models` container, generate a SAS URL.
3. Update the Container App env: `MODEL_VERSION=v1.1.0`,
   `MODEL_WEIGHTS_URL=<sas-url>` (as a secret). On restart the backend
   downloads the file once, verifies its SHA-256 against the registry, and
   loads it. Rollback = set `MODEL_VERSION=v1.0.0` back.

## 6. Dataset versioning (data side of the lifecycle)

The dataset lives in the Deliverable-B repo, not here. To archive it as the
registered `broccoli-rgb-v1`:

```bash
# Writes manifest.json INTO the dataset dir, so it travels inside the zip
python3 scripts/data/make_manifest.py /path/to/dataset --version broccoli-rgb-v1
zip -r broccoli-rgb-v1.zip /path/to/dataset
# Prints the zip's sha256 as a paste-ready registry line
python3 scripts/data/make_manifest.py --archive broccoli-rgb-v1.zip
scripts/data/upload_dataset.sh --account teamb4broccolist \
  --archive broccoli-rgb-v1.zip --version broccoli-rgb-v1   # container defaults to "datasets"
```

Then fill in `archive_sha256`, `num_images`, and the split sizes in
[`data/registry.json`](../data/registry.json), replacing the
`<team-storage-account>` placeholder.

## 7. Monitoring & the retraining demo (local)

Monitoring runs locally on purpose — for a PoC, a cloud-hosted monitoring
service adds cost without adding insight (see `monitoring/README.md`):

```bash
docker compose up -d --build      # the app on :8080, metrics on the compose network
make monitor-up                   # Prometheus :9090 + Grafana :3000 (dashboard auto-provisioned)
make drift                        # inject 30 synthetic bad-condition images
python3 scripts/retraining/check_triggers.py --window 15m   # T2 fires, exit code 1
```

Grafana: http://localhost:3000 → dashboard "BroccoliDetect - Operational & ML".

## 8. Cost hygiene (course rules)

- Create a **budget with an 80% email alert** on the resource group
  (Portal → Cost Management → Budgets, e.g. €10/month).
- Once the deployment has been demonstrated and documented:
  `az containerapp delete`, delete old ACR images, and remove anything unused.
  The registry and the storage account are the usual silent spenders.
