# Wasabi SDK Schema Reference

Each resource class exposes a `to_dict()` method that returns its properties as a dictionary.
The schemas below document the shape of those dictionaries.

> This file is auto-generated from the schema definitions in `src/wasabi/client.py`.
> Last generated: 2026-03-12T20:51:30Z
> To regenerate: `uv run python scripts/generate_schema.py`

## User

| Key | Type | Description |
|-----|------|-------------|
| `name` | `str` | Username |
| `arn` | `str` | IAM ARN |
| `api-keys` | `dict` | Access key ID mapped to `{"secret-key": str, "status": str}`. Max 2 keys per user. |

```json
{
    "name": "jimbob",
    "arn": "arn:aws:iam::123456789012:user/jimbob",
    "api-keys": {
        "AKIAIOSFODNN7EXAMPLE": {
            "secret-key": "",
            "status": "Active"
        },
        "AKIAI44QH8DHBEXAMPLE": {
            "secret-key": "",
            "status": "Disabled"
        }
    }
}
```

## Group

| Key | Type | Description |
|-----|------|-------------|
| `name` | `str` | Group name |
| `arn` | `str` | IAM ARN |
| `members` | `list[str]` | Member ARNs |
| `attached-policies` | `list[str]` | Attached managed policy ARNs |
| `inline-policies` | `dict` | Policy name mapped to policy document |

```json
{
    "name": "admins",
    "arn": "arn:aws:iam::123456789012:group/admins",
    "members": [
        "jimbob",
        "jane"
    ],
    "attached-policies": [
        "arn:aws:iam::123456789012:policy/admin-policy"
    ],
    "inline-policies": {
        "admin-policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "s3:*",
                    "Resource": "*"
                }
            ]
        }
    }
}
```

## Policy

| Key | Type | Description |
|-----|------|-------------|
| `name` | `str` | Policy name |
| `arn` | `str` | IAM ARN |
| `version` | `str` | Version ID (e.g. `"v1"`) |
| `is-default-version` | `bool` | Whether this is the default version |
| `actions` | `list[str]` | Allowed S3 actions |
| `resources` | `list[str]` | Resource ARNs the policy applies to |

```json
{
    "name": "dev-policy",
    "arn": "arn:aws:iam::123456789012:policy/dev-policy",
    "version": "v1",
    "is-default-version": true,
    "actions": [
        "s3:AbortMultiPartUpload",
        "s3:DeleteObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:PutObject"
    ],
    "resources": [
        "arn:aws:s3::123456789012:bucket1"
    ]
}
```

## Bucket

| Key | Type | Description |
|-----|------|-------------|
| `name` | `str` | Bucket name |
| `arn` | `str` | S3 ARN |
| `region` | `str` | Wasabi region (e.g. `"us-east-1"`) |
| `storage_class` | `str` | Always `"hot"` for Wasabi |
| `bucket_policy` | `dict` | Bucket policy document (empty if none) |
| `lifecycle-rules` | `dict` | Lifecycle configuration (empty if none) |
| `versioning` | `bool` | Whether versioning is enabled |
| `gb_used` | `float` | Storage used in GB |
| `object_count` | `int` | Number of objects |

```json
{
    "name": "my_bucket",
    "arn": "arn:aws:s3:::my_bucket",
    "region": "us-west-1",
    "storage_class": "hot",
    "bucket_policy": {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "FullAccess",
                "Effect": "Allow",
                "Principal": {
                    "AWS": [
                        "arn:aws:iam::123456789012:group/devs"
                    ]
                },
                "Action": [
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    "arn:aws:s3:::my_bucket",
                    "arn:aws:s3:::my_bucket/*"
                ]
            }
        ]
    },
    "lifecycle-rules": {},
    "versioning": false,
    "gb_used": 1234.567,
    "object_count": 381579
}
```

## Full Example

A complete state export combining all resource types:

```json
{
    "users": [
        "..."
    ],
    "groups": [
        "..."
    ],
    "policies": [
        "..."
    ],
    "buckets": [
        "..."
    ]
}
```

See `to_dict()` on each class (`User`, `Group`, `Policy`, `Bucket`) to export individual resources.
