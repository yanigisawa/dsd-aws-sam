{{ current_settings }}

# AWS SAM settings.
import os

if os.environ.get("ON_AWS_SAM"):
    # Debug setting from environment variable.
    DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1")

    # Read SECRET_KEY from environment (set via Secrets Manager in SAM template).
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", SECRET_KEY)

    # Allow all hosts -- API Gateway handles domain routing.
    ALLOWED_HOSTS = ["*"]

    # CSRF trusted origins for API Gateway.
    # Update this if you add a custom domain.
    CSRF_TRUSTED_ORIGINS = [
        "https://*.execute-api.{{ aws_region }}.amazonaws.com",
    ]
{% if db_engine == "postgres" %}
    # Database configuration from DATABASE_URL (RDS PostgreSQL).
    import dj_database_url

    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        DATABASES["default"] = dj_database_url.parse(db_url)
{% endif %}
    # Static files on S3.
    STORAGES = {
        "staticfiles": {
            "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
        },
    }
    AWS_STORAGE_BUCKET_NAME = os.environ.get("STATIC_FILES_BUCKET", "")
    AWS_S3_REGION_NAME = os.environ.get("AWS_REGION", "{{ aws_region }}")
    AWS_DEFAULT_ACL = None
    STATIC_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/static/"

    # CloudWatch-compatible logging.
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "[%(levelname)s] %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "INFO",
        },
    }
