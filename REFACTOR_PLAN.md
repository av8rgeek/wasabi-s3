# Wasabi Python SDK — Refactor Plan

## Project Context

A Python SDK wrapping Wasabi cloud storage APIs (S3-compatible + IAM + Billing). 5 source files (~750 LOC), LGPL-2.1 licensed. Currently a flat package at repo root with no packaging infrastructure. The goal is to refactor for quality, security, and publish-readiness on PyPI.

**Branch**: `refactor/analyze-and-improve`

**Source Files**:
- `wasabi.py` — Base `Wasabi` class, `WasabiEndpoints` enum, `DateTimeEncoder`, `WasabiBillingApiAuthorization`
- `bucket.py` — `WasabiBucket(Wasabi)` — bucket CRUD, policy, lifecycle, versioning, billing
- `user.py` — `WasabiUser(Wasabi)` — user CRUD, API key management
- `group.py` — `WasabiGroup(Wasabi)` — group CRUD, membership, inline/attached policies
- `policy.py` — `WasabiPolicy(Wasabi)` — managed policy CRUD, versioning
- `__init__.py` — Public exports

**Dependencies** (detected from imports, not declared anywhere):
- `boto3`
- `botocore`
- `requests`
- `aws-requests-auth`

---

## Phase 1 — Fix Critical Bugs

### 1.1 Mutable default arguments
- **`bucket.py:15`** — `billing_data: dict={}` in `__init__`
- **`bucket.py:253`** — `billing_data: dict={}` in `get_bucket_size_gb`
- **`bucket.py:278`** — `billing_data: dict={}` in `get_bucket_object_count`
- **Fix**: Change defaults to `None`, assign `{}` inside the method body.

### 1.2 `user_exists()` can return `None`
- **`user.py:37-42`** — If `ClientError` code is not `"NoSuchEntity"`, no return statement → returns `None`.
- **Fix**: Log the error and return `False` (or re-raise).

### 1.3 `delete_user()` return type annotation wrong
- **`user.py:70`** — Annotated as `-> dict` but returns `bool`.
- **Fix**: Change to `-> bool`.

### 1.4 `delete_all_api_keys` sets `api-keys` to list, schema expects dict
- **`user.py:192`** — `self.__properties["api-keys"] = []` should be `{}`.

### 1.5 `get_api_keys` return type wrong
- **`user.py:96`** — Annotated `-> list` but returns a `dict`.
- **Fix**: Change to `-> dict`.

### 1.6 `list_objects` returns `None` on error
- **`bucket.py:225`** — Annotated `-> dict` but returns `None` on error.
- **Fix**: Return `{}` on error.

### 1.7 `DateTimeEncoder.default` missing super() call
- **`wasabi.py:14-16`** — Non-date objects silently return `None` instead of raising `TypeError`.
- **Fix**: Add `return super().default(obj)` at end of method.

### 1.8 `self.arn` accessed before assignment in `WasabiGroup`
- **`group.py:18`** — `self.__properties["arn"] = self.arn` depends on `group_exists()` setting `self.arn` as a side effect. If group not found, `AttributeError`.
- **Fix**: Initialize `self.arn = ""` before calling `group_exists()`, or restructure so `group_exists` returns the ARN.

### 1.9 `__properties` annotated as `list` in `WasabiUser`
- **`user.py:21`** — `self.__properties: list = ...` should be `: dict`.

---

## Phase 2 — Fix Security Issues

### 2.1 Make credentials private
- **`wasabi.py:358-359`** — `self.aws_access_key_id` and `self.aws_secret_access_key` are public.
- **Fix**: Rename to `self._access_key_id` / `self._secret_access_key`. Update all references in child classes.

### 2.2 Replace `assert` with `raise ValueError`
- **`wasabi.py:371-373`** — `assert` is stripped with `python -O`.
- **Fix**: `if not (key and secret): raise ValueError("Missing Wasabi credentials")`

### 2.3 Handle `None` from `getenv()`
- **`wasabi.py:358-359`** — `getenv()` returns `None` when unset, but validation only checks for `""`.
- **Fix**: Use `getenv("WASABI_ACCESS_KEY", "")` or check for `None` explicitly.

### 2.4 Parameterize `export_billing_data`
- **`wasabi.py:514`** — Hardcoded `"billing_data.json"` relative path.
- **Fix**: Accept `path: str` parameter, default to a reasonable value.

### 2.5 Input validation
- Add validation in constructors: `bucket_name`, `user_name`, `policy_name`, `group_name` must be non-empty strings.
- Validate region before API calls.

---

## Phase 3 — Restructure to `src/` Layout

```
wasabi/
├── src/
│   └── wasabi/
│       ├── __init__.py
│       ├── client.py          (renamed from wasabi.py — base class)
│       ├── bucket.py
│       ├── user.py
│       ├── group.py
│       ├── policy.py
│       ├── endpoints.py       (extracted from wasabi.py)
│       ├── exceptions.py      (custom exception classes)
│       ├── _billing.py        (billing auth, extracted from wasabi.py)
│       └── py.typed
├── tests/
│   ├── __init__.py
│   ├── test_client.py
│   ├── test_bucket.py
│   ├── test_user.py
│   ├── test_group.py
│   └── test_policy.py
├── pyproject.toml
├── README.md
├── LICENSE
└── .gitignore
```

- Move schema templates to class-level constants (out of `__init__`).
- Extract `WasabiEndpoints` and `S3_ENDPOINTS` into `endpoints.py`.
- Extract `WasabiBillingApiAuthorization` and `DateTimeEncoder` into `_billing.py`.
- Replace name-mangled schema access (`self._Wasabi__schema_*`) with protected methods or class attributes.

---

## Phase 4 — Standardize Naming

### Class renames (drop redundant `Wasabi` prefix)
| Current | New | Usage becomes |
|---------|-----|---------------|
| `WasabiBucket` | `Bucket` | `wasabi.Bucket` |
| `WasabiUser` | `User` | `wasabi.User` |
| `WasabiGroup` | `Group` | `wasabi.Group` |
| `WasabiPolicy` | `Policy` | `wasabi.Policy` |
| `WasabiEndpoints` | `Endpoint` | `wasabi.Endpoint` |
| `Wasabi` (base) | `Client` | `wasabi.Client` |

### Method renames
| Current | New | Reason |
|---------|-----|--------|
| `export_properties` | `to_dict` | Python convention |
| `_new_client` | `_create_client` | Clearer intent |
| `get_members_username` | `get_member_usernames` | Plural consistency |
| `get_members_arn` | `get_member_arns` | Plural consistency |
| `get_bucket_size_gb` | `get_storage_size_gb` | Context already established |
| `get_bucket_object_count` | `get_object_count` | Context already established |
| `get_example_schema` | Remove entirely | Not useful for consumers |

### Schema key consistency
Standardize to `snake_case` throughout:
- `api-keys` → `api_keys`
- `attached-policies` → `attached_policies`
- `inline-policies` → `inline_policies`
- `lifecycle-rules` → `lifecycle_rules`
- `is-default-version` → `is_default_version`
- `secret-key` → `secret_key`

---

## Phase 5 — Type Annotations & Code Quality

### 5.1 Fix type annotations
- `botocore.client` → `botocore.client.BaseClient` everywhere
- Add `Optional[...]` where methods can return `None`
- Add missing return type annotations on all `group.py` methods
- Use `list[dict]` consistently (not bare `list`)

### 5.2 Replace `print()` with logger
- **`bucket.py:264, 289`** — `print("Getting billing data...")` → `self.__logger.debug(...)`

### 5.3 Replace generic exceptions
- **`wasabi.py:378`** — `raise Exception(f"Invalid Wasabi region...")` → custom `InvalidRegionError`
- **`wasabi.py:506`** — `raise Exception(f"Failed to get query...")` → custom `BillingApiError`

### 5.4 Fix `bucket_exists` to use `head_bucket`
- **`bucket.py:62-71`** — Replace `list_buckets()` iteration with `head_bucket()` call.

### 5.5 Fix N+1 client creation in `get_buckets`
- **`wasabi.py:419-421`** — `__get_bucket_location` creates a new client per call inside a loop. Reuse the client.

### 5.6 Remove unused logger in `__init__.py`
- **`__init__.py:9`** — `loggers = logging.getLogger(__name__)` is unused.

### 5.7 Remove monkey-patched `S3_ENDPOINTS`
- **`wasabi.py:54-72`** — Move to a module-level constant or classmethod in `endpoints.py`.

---

## Phase 6 — Add Missing Methods

### Bucket
- `set_versioning(enabled: bool)` — Toggle versioning
- `set_lifecycle(rules: dict)` — Set lifecycle configuration
- `set_bucket_policy(policy: dict)` — Set bucket policy
- `delete_bucket_policy()` — Remove bucket policy

### User
- `get_groups() -> list[str]` — List groups a user belongs to
- `enable_api_key(key_id: str)` — Activate a key
- `disable_api_key(key_id: str)` — Deactivate a key

### Policy
- `detach_from_all()` — Detach from all groups/users (prerequisite for delete)
- `list_versions() -> list[dict]` — List policy versions
- `delete_version(version_id: str)` — Delete a specific version

### Client (base)
- `get_account_id() -> str` — Public utility (currently only used internally in policy)

### General
- Context manager support (`__enter__`/`__exit__`) on resource classes

---

## Phase 7 — Remove / Rework

- **`get_example_schema()`** — Remove. Replace with proper documentation or TypedDict/dataclass schemas.
- **`get_inline_group_policy()`** (`group.py:124`) — Missing `policy_name` param, nearly useless. Remove or fix to accept the parameter.
- **`export_billing_data()`** — Accept a `path` parameter or remove from public API.

---

## Phase 8 — Packaging for PyPI

### 8.1 Create `pyproject.toml`
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "wasabi-cloud"
version = "0.1.0"
description = "Python SDK for Wasabi Cloud Storage"
license = "LGPL-2.1-or-later"
requires-python = ">=3.10"
dependencies = [
    "boto3",
    "requests",
    "aws-requests-auth",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "mypy", "ruff"]
```

### 8.2 Add `__version__` to `__init__.py`

### 8.3 Add `py.typed` marker file

### 8.4 Add `README.md` with usage examples

### 8.5 Update `__all__` exports to use new class names

---

## Phase 9 — Tests

- Unit tests for each class with mocked boto3 clients
- Integration test examples (marked as requiring credentials)
- Test edge cases: empty names, invalid regions, None credentials, API errors

---

## Phase 10 — CI / Publishing

- GitHub Actions workflow for lint + type check + tests
- Publishing workflow for PyPI (on tag/release)
