# FraudGuard – DevSecOps Edition
DevSecOps Lab CIAP Microproject · topic: Path and Condition Testing of an AI-Based Fraud Detection Prototype · SDG 9

A Flask website (hybrid rules + ML fraud detector) with a full DevSecOps toolchain:
GitHub · Docker · Jenkins · SonarQube · Trivy · Terraform · AWS EC2 · JIRA.

```
fraud_detector/    Flask app, rule engine, model          tests/       120 pytest tests
templates/ static/ web page (no inline JS/CSS, strict CSP)  Dockerfile   non-root image
Jenkinsfile        10-stage pipeline                       terraform/   AWS EC2 + security group
tools/             docker-compose for Jenkins + SonarQube  scripts/     vuln_summary.py (report tables)
```

## Run order (do these in order; about 2-3 hours the first time)

### 0. Quick check on your laptop (optional)
```
pip install -r requirements-dev.txt
python -m pytest -q
python run.py            # http://127.0.0.1:5000
```
If scikit-learn is blocked on your laptop, the app uses its built-in NumPy model automatically.
(One test, test_model_metrics_reasonable_and_reproducible, needs scikit-learn; skip it with `-k "not reproducible"`.)

### 1. GitHub
Create an empty repo named `fraudguard-devsecops` on github.com (public is easiest for Jenkins), then:
```
git init
git add .
git commit -m "FraudGuard DevSecOps microproject"
git branch -M main
git remote add origin https://github.com/<your-user>/fraudguard-devsecops.git
git push -u origin main
```
Never commit passwords, AWS keys or `.tfvars` (the `.gitignore` already blocks them).

### 2. Docker
```
docker build -t fraudguard:1 .
docker run -d --name fraudguard -p 5000:5000 fraudguard:1
docker ps
curl http://localhost:5000/api/health
```
Open http://localhost:5000. Screenshots: `docker build` output, `docker ps` (shows "healthy" after ~30 s), the website.
Stop it before the pipeline run: `docker rm -f fraudguard`

### 3. Jenkins + SonarQube
```
docker compose -f tools/docker-compose.yml up -d --build
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```
* Jenkins: http://localhost:8080 -> paste the password -> Install suggested plugins -> create admin user.
* SonarQube (wait 2-3 min): http://localhost:9000 -> login `admin` / `admin` -> set a new password ->
  top-right avatar -> My Account -> Security -> Generate Token (type: User token) -> copy it.
* Jenkins -> Manage Jenkins -> Credentials -> (global) -> Add Credentials -> Kind: **Secret text**,
  Secret: the Sonar token, ID: **sonar-token**.
* Jenkins -> New Item -> name `fraudguard` -> **Pipeline** -> Pipeline script from SCM -> Git ->
  your repo URL -> branch `*/main` -> Script Path `Jenkinsfile` -> Save -> **Build Now**.
* After the first build the button becomes "Build with Parameters" (QUALITY_GATE, FAIL_ON_CRITICAL, PUSH_IMAGE).
* The first run downloads the Trivy database and images, so it takes longer (10-15 min).

Screenshots: Jenkins stage view (all green), console output of the Trivy stages, SonarQube project dashboard, Jenkins build artifacts.

### 4. Vulnerability report
```
docker cp jenkins:/var/jenkins_home/workspace/fraudguard/reports ./reports
python scripts/vuln_summary.py reports
```
Copy the numbers/tables into Section 5 of the report. Take screenshots of the Trivy table output in the Jenkins console and of the SonarQube Issues / Security Hotspots tabs.

### 5. Push the image to Docker Hub (needed for AWS)
```
docker login
docker tag fraudguard:1 <dockerhub-user>/fraudguard:latest
docker push <dockerhub-user>/fraudguard:latest
```
(or run the pipeline with PUSH_IMAGE ticked after adding a `dockerhub-creds` Username/Password credential).
The Docker Hub repository must be **public** so the server can pull it without a login.

### 6. Terraform on AWS
Install Terraform and the AWS CLI, create an IAM user with programmatic access (EC2 permissions), run `aws configure`.
```
cd terraform
copy terraform.tfvars.example terraform.tfvars    (then edit docker_image)
terraform init
terraform plan
terraform apply
```
Open the `website_url` output after 2-3 minutes. Screenshots: `terraform plan` summary, `terraform apply` complete with outputs, the EC2 console, the website on the public IP.
**When finished: `terraform destroy`** so you are not charged. Hide AWS keys and account IDs in the video and screenshots.

### 7. Demo video (3-5 minutes)
Website -> `docker ps` -> Jenkins stage view -> SonarQube + Trivy results -> Terraform files and AWS console -> website on AWS. Post on LinkedIn. Check that no password/key is visible.

## Troubleshooting
* **Docker / Terraform blocked by a laptop security policy:** run the steps on a college lab PC, GitHub Codespaces, or an EC2/Cloud9 machine instead.
* **SonarQube does not start / keeps restarting:** give Docker Desktop at least 4 GB RAM (Settings -> Resources).
* **Trivy "TOOMANYREQUESTS" when downloading its database:** add `-e TRIVY_DB_REPOSITORY=public.ecr.aws/aquasecurity/trivy-db` to the `docker run ... aquasec/trivy` commands in the Jenkinsfile.
* **`docker: not found` inside Jenkins:** rebuild the stack with `--build`; the socket mount must exist.
* **Scanner stage fails on `--volumes-from jenkins`:** the Jenkins container must be named `jenkins` (it is, in the compose file).
