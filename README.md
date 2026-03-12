# wasabi-s3

A Python SDK for managing [Wasabi Cloud Storage](https://wasabi.com) resources. Wraps Wasabi's S3-compatible and IAM APIs into a friendly interface for managing buckets, users, groups, and policies.

## Installation

```bash
pip install wasabi-s3
```

Requires Python 3.13+.

## Configuration

Set your Wasabi credentials as environment variables:

```bash
export WASABI_ACCESS_KEY="your-access-key"
export WASABI_SECRET_KEY="your-secret-key"
```

## Quick Start

### Buckets

```python
from wasabi_s3 import Bucket

# Create a bucket in us-east-1 (default)
bucket = Bucket("my-bucket")
bucket.create_bucket()

# Create a bucket in a specific region
bucket = Bucket("my-bucket", region="eu-central-1")

# Manage versioning
bucket.set_versioning(True)
print(bucket.get_versioning())  # True

# Set a lifecycle rule
bucket.set_lifecycle({"Rules": [{"Status": "Enabled", "Prefix": "", "Expiration": {"Days": 90}}]})

# Get bucket properties
print(bucket.to_dict())

# Delete (even if not empty)
bucket.force_delete_bucket()
```

### Users

```python
from wasabi_s3 import User

user = User("jimbob")
user.create_user()

# API key management
key = user.create_api_key()  # Returns {key_id: {secret-key, status}}
user.disable_api_key("AKIA...")
user.enable_api_key("AKIA...")
user.delete_api_key("AKIA...")

# List groups the user belongs to
groups = user.list_groups()

print(user.to_dict())
```

### Groups

```python
from wasabi_s3 import Group

group = Group("developers")
group.create_group()

# Membership
group.add_member("jimbob")
group.remove_member("jimbob")

# Attach a managed policy
group.attach_managed_policy("arn:aws:iam::123456789012:policy/dev-policy")

# Inline policies
group.put_inline_group_policy({
    "Version": "2012-10-17",
    "Statement": [{"Sid": "AllowS3", "Effect": "Allow", "Action": "s3:*", "Resource": "*"}]
})

print(group.to_dict())
```

### Policies

```python
from wasabi_s3 import Policy

policy = Policy("dev-policy")
policy.create_policy({
    "Version": "2012-10-17",
    "Statement": [{
        "Sid": "dev-policy",
        "Effect": "Allow",
        "Action": ["s3:GetObject", "s3:PutObject"],
        "Resource": ["arn:aws:s3:::my-bucket/*"]
    }]
})

# Update creates a new version
policy.update_policy({...})

# List and manage versions
policy.list_versions()
policy.delete_version("v1")

# Clean up
policy.detach_from_all()
policy.delete_policy()
```

## Schema Reference

Each resource class has a `to_dict()` method that returns a dictionary of its properties. See [SCHEMA.md](SCHEMA.md) for the full schema documentation.

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=wasabi_s3 --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# Type check
uv run mypy src/
```

## License

LGPL-2.1-or-later
