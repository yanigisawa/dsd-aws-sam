# dsd-aws-sam

An [AWS Lambda](https://aws.amazon.com/lambda/) deployment plugin for [django-simple-deploy](https://github.com/django-simple-deploy/django-simple-deploy). Configures Django projects to deploy as serverless applications using [AWS SAM](https://aws.amazon.com/serverless/sam/) with [Mangum](https://mangum.io/) as the ASGI-to-Lambda adapter.

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

```bash
pip install dsd-aws-sam
```

Or for development:

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

### SQLite (default)

Uses Lambda's ephemeral `/tmp` storage. Suitable for demos and stateless apps — data does not persist across Lambda invocations.

```bash
python manage.py deploy --automate-all
```

### PostgreSQL

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

Typical recovery flow:

To view detailed deployment errors, check CloudFormation stack events:

```
aws cloudformation describe-stack-events --stack-name blog-dev --region us-east-1
```

To rollback the stack to a clean state before redeploying:

```
sam delete --stack-name blog-dev --region us-east-1
```

Rebuild and redeploy:

```
sam build
sam deploy --stack-name blog-dev --region us-east-1
```
