# dsd-aws-sam

An [AWS Lambda](https://aws.amazon.com/lambda/) deployment plugin for [django-simple-deploy](https://github.com/django-simple-deploy/django-simple-deploy). Configures Django projects to deploy as serverless applications using [AWS SAM](https://aws.amazon.com/serverless/sam/) with [Mangum](https://mangum.io/) as the ASGI-to-Lambda adapter.

> **Project status (alpha):**
> - Not published to PyPI — install from GitHub (see [Installation](#installation)).
> - The default **SQLite** deployment is **read-only** at runtime. Lambda's filesystem is read-only, so any Django write (admin, ORM `.save()`, migrations against the deployed DB, etc.) will raise an error. Suitable only for demos that read pre-populated data.
> - The **PostgreSQL / RDS** path is **experimental** — the template is in place but has not been tested end-to-end.

## Prerequisites

- Python 3.10+
- Django 4.2+
- [AWS CLI](https://aws.amazon.com/cli/) — installed and configured with valid credentials
- [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html#:~:text=We%20recommend%20using%20one%20of,SAM%20CLI%2C)
- [Docker](https://www.docker.com/) — used by SAM to build Lambda packages in isolated containers

Verify your setup:

```bash
aws --version
aws sts get-caller-identity   # confirms credentials are configured
sam --version
docker --version
```

## Installation

> **Status:** This plugin is in alpha and is **not yet published to PyPI**. Install directly from GitHub.

Install the latest version from GitHub:

```bash
pip install git+https://github.com/django-simple-deploy/dsd-aws-sam.git
```

Or for development (clone the repo first, then from the project root):

```bash
pip install -e ".[dev]"
```

## Quick Start

Add `django_simple_deploy` to `INSTALLED_APPS` in your `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "django_simple_deploy",
]
```

From your Django project root:

```bash
# Configuration only — generates deployment files without deploying
python manage.py deploy

# Full deployment — generates files, builds, and deploys to AWS
python manage.py deploy --automate-all
```

If you run without `--automate-all`, deploy manually:

```bash
sam build
sam deploy
```

## CLI Options

All options are passed through the `manage.py deploy` command:

| Option             | Default                                           | Description                                                      |
| ------------------ | ------------------------------------------------- | ---------------------------------------------------------------- |
| `--aws-region`     | Auto-detected from AWS CLI config, or `us-east-1` | AWS region for deployment                                        |
| `--aws-stack-name` | `<project>-<stage>`                               | CloudFormation stack name                                        |
| `--db-engine`      | `sqlite`                                          | Database engine: `sqlite` or `postgres`                          |
| `--architecture`   | `arm64`                                           | Lambda CPU architecture: `arm64` (Graviton, cheaper) or `x86_64` |
| `--stage`          | `dev`                                             | Deployment stage: `dev`, `staging`, or `prod`                    |

### Examples

```bash
# Deploy with PostgreSQL (provisions RDS) in us-west-2
python manage.py deploy --automate-all \
    --db-engine postgres --aws-region us-west-2

# Deploy with x86_64 architecture to a custom stack name
python manage.py deploy --automate-all \
    --architecture x86_64 --aws-stack-name my-app-production --stage prod
```

## Database Options

### SQLite (default) — read-only

The SQLite database file is bundled into the Lambda deployment package. Lambda's filesystem is **read-only** at runtime (only `/tmp` is writable, and this plugin does not relocate the SQLite file there), so:

- **Reads work.** Any view that only queries the database will function.
- **Writes fail.** Any attempt to write — admin edits, `Model.save()`, form submissions, running `migrate` against the deployed DB — will raise a Django database write error.

This makes the SQLite path suitable only for demos serving pre-populated, read-only content. For any app that writes to the database, use `--db-engine postgres` (currently experimental — see below) or wait for a future release that copies the SQLite file to `/tmp` on cold start.

```bash
python manage.py deploy --automate-all
```

### PostgreSQL — experimental, not yet end-to-end tested

> **Warning:** The RDS / PostgreSQL deployment path has **not been tested end-to-end** by the maintainer. The CloudFormation template is in place and should work in theory, but expect rough edges. Please file issues if you try it.

Provisions a full RDS PostgreSQL instance with supporting VPC infrastructure (private subnets, NAT gateway, security groups). Adds `psycopg2-binary` and `dj-database-url` to your requirements. The database password is stored in AWS Secrets Manager.

```bash
python manage.py deploy --automate-all --db-engine postgres
```

**Note:** The PostgreSQL path creates significantly more AWS resources (VPC, subnets, NAT gateway, RDS instance) and will incur ongoing costs even when idle.

## What Gets Generated

The plugin creates or modifies these files in your project:

| File                                  | Purpose                                                                                                                                                                                       |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lambda_handler.py`                   | Mangum-based entry point that routes API Gateway events to Django and supports management commands via `{"manage": "..."}` payloads                                                           |
| `template.yaml`                       | SAM/CloudFormation template defining Lambda, API Gateway, S3, and Secrets Manager resources (or `template_with_rds.yaml` resources for postgres)                                              |
| `samconfig.toml`                      | SAM CLI build and deploy configuration                                                                                                                                                        |
| `.github/workflows/deploy_lambda.yml` | GitHub Actions CI/CD workflow (requires `AWS_ROLE_ARN` secret for OIDC auth)                                                                                                                  |
| `static/.gitkeep`                     | Placeholder for Django static files                                                                                                                                                           |
| `settings.py`                         | Appends a conditional block that activates when `ON_AWS_LAMBDA=1` — configures SECRET_KEY from Secrets Manager, S3-backed static files via django-storages, and CloudWatch-compatible logging |
| `requirements.txt`                    | Adds `mangum`, `django-storages`, `boto3` (plus `psycopg2-binary`, `dj-database-url` for postgres)                                                                                            |

## Post-Deployment

When using `--automate-all`, the plugin automatically:

1. Commits generated files
2. Runs `sam build` and `sam deploy`
3. Invokes the Lambda to run `collectstatic` (uploads static files to S3)
4. Invokes the Lambda to run `migrate` (initializes the database)
5. Displays the deployed API URL

To run management commands on the deployed Lambda manually:

```bash
aws lambda invoke --function-name <function-name> \
    --payload '{"manage": "migrate"}' output.json
```

## Tearing Down the Deployment

When you're done with a deployed stack, you can delete **all** AWS resources created by the plugin (Lambda, API Gateway, S3 bucket, Secrets Manager entry, and — for the postgres path — the VPC, subnets, NAT gateway, and RDS instance) in one of two ways.

### Option 1: `sam delete` (recommended)

From the project root:

```bash
sam delete --stack-name <stack-name> --region <region>
```

Use the stack name and region you deployed with (defaults: `<project>-<stage>` and your configured AWS region). SAM will prompt for confirmation and then delete the CloudFormation stack and all its resources.

### Option 2: Delete the stack from the AWS Console

1. Open the [AWS CloudFormation console](https://console.aws.amazon.com/cloudformation/) in the region you deployed to.
2. Find the stack matching your `--aws-stack-name` (default `<project>-<stage>`).
3. Select it and click **Delete**.

Both options remove the entire deployed project. The S3 static-files bucket must be empty before the stack will delete cleanly; if deletion stalls on the bucket, empty it from the S3 console and retry.

> **Note:** The PostgreSQL path may also leave behind RDS automated snapshots depending on your account settings — check the RDS console if you want a truly clean teardown.

## Package Dependencies Added

The plugin adds these packages to your project's `requirements.txt`:

- **mangum** — ASGI adapter for Lambda
- **django-storages** — S3 static file storage backend
- **boto3** — AWS SDK
- **psycopg2-binary** — PostgreSQL adapter (postgres only)
- **dj-database-url** — `DATABASE_URL` parser (postgres only)

## Development

Use this command to avoid generating all local .pyc files during development:

```bash
export PYTHONDONTWRITEBYTECODE=1
```

## Troubleshooting

To view detailed deployment errors, check CloudFormation stack events:

```
aws cloudformation describe-stack-events --stack-name blog-dev --region us-east-1
```

If a deployment is wedged and won't recover, tear the stack down (see [Tearing Down the Deployment](#tearing-down-the-deployment)) and redeploy:

```
sam build
sam deploy --stack-name blog-dev --region us-east-1
```
