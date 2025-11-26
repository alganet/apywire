<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Examples

Illustrative examples showing how apywire can be used to wire objects in Python applications.

## Configuration Management

Centralize configuration and inject it into services:

```python
from apywire import Wiring
import os

spec = {
    # Configuration constants
    "db_host": os.getenv("DB_HOST", "localhost"),
    "db_port": int(os.getenv("DB_PORT", "5432")),
    "db_name": os.getenv("DB_NAME", "myapp"),
    "redis_url": os.getenv("REDIS_URL", "redis://localhost"),
    "debug": os.getenv("DEBUG", "false") == "true",

    # Build database URL from config
    "MyApp app": {
        "db_host": "{db_host}",
        "db_port": "{db_port}",
        "db_name": "{db_name}",
        "redis_url": "{redis_url}",
        "debug": "{debug}",
    },
}

wired = Wiring(spec)
app = wired.app()
```

## Database Connection Pool

Set up a connection pool with dependency injection:

```python
from apywire import Wiring

spec = {
    # Configuration
    "database_url": "postgresql://localhost/mydb",
    "pool_min": 1,
    "pool_max": 20,

    # Connection pool
    "psycopg2.pool.ThreadedConnectionPool pool": {
        "minconn": "{pool_min}",
        "maxconn": "{pool_max}",
        "dsn": "{database_url}",
    },

    # Repository using the pool
    "MyRepository users": {
        "pool": "{pool}",
        "table_name": "users",
    },
}

wired = Wiring(spec, thread_safe=True)

# Access repository
users_repo = wired.users()
```

## Multi-Layer Architecture

Service layer with repositories and caching:

```python
from apywire import Wiring

spec = {
    # Infrastructure layer
    "psycopg2.connect database": {
        "dsn": "postgresql://localhost/mydb",
    },
    "redis.Redis cache": {
        "host": "localhost",
        "port": 6379,
    },

    # Repository layer
    "UserRepository user_repo": {
        "db": "{database}",
    },
    "ProductRepository product_repo": {
        "db": "{database}",
    },

    # Service layer
    "UserService user_service": {
        "repo": "{user_repo}",
        "cache": "{cache}",
    },
    "ProductService product_service": {
        "repo": "{product_repo}",
        "cache": "{cache}",
    },

    # Application layer
    "Application app": {
        "user_service": "{user_service}",
        "product_service": "{product_service}",
    },
}

wired = Wiring(spec, thread_safe=True)
app = wired.app()
```

## FastAPI Integration

Use apywire with FastAPI for dependency injection:

```python
from fastapi import FastAPI, Depends
from apywire import Wiring

# Define your wiring spec
spec = {
    "database_url": "postgresql://localhost/mydb",
    "psycopg2.connect db": {"dsn": "{database_url}"},
    "UserRepository user_repo": {"db": "{db}"},
    "UserService user_service": {"repo": "{user_repo}"},
}

# Create wiring container
wired = Wiring(spec, thread_safe=True)

# Create FastAPI app
app = FastAPI()

# Dependency providers
async def get_user_service():
    """Provide UserService via dependency injection."""
    return await wired.aio.user_service()

# Route using dependency
@app.get("/users/{user_id}")
async def get_user(user_id: int, service = Depends(get_user_service)):
    """Get user by ID."""
    user = await service.get_user(user_id)
    return user
```

## Testing with Mocks

Replace real dependencies with mocks for testing:

```python
from apywire import Wiring
from unittest.mock import Mock, MagicMock
import pytest

# Production spec
production_spec = {
    "psycopg2.connect db": {"dsn": "postgresql://prod/db"},
    "redis.Redis cache": {"url": "redis://prod"},
    "EmailService email": {"api_key": "real-api-key"},
    "UserService user_service": {
        "db": "{db}",
        "cache": "{cache}",
        "email": "{email}",
    },
}

# Test spec with mocks
test_spec = {
    "unittest.mock.Mock db": {},
    "unittest.mock.Mock cache": {},
    "unittest.mock.Mock email": {},
    "UserService user_service": {
        "db": "{db}",
        "cache": "{cache}",
        "email": "{email}",
    },
}

# Pytest fixture
@pytest.fixture
def wired():
    return Wiring(test_spec)

# Test
def test_user_service(wired):
    service = wired.user_service()

    # Configure mocks
    wired.db().execute = MagicMock(return_value=[{"id": 1, "name": "Alice"}])

    # Test your service
    users = service.get_users()
    assert len(users) > 0
```

## Environment-Based Configuration

Different specs for different environments:

```python
from apywire import Wiring
import os

def get_spec(env: str):
    """Get spec based on environment."""
    base_spec = {
        "log_level": "DEBUG" if env == "dev" else "INFO",
    }

    if env == "production":
        base_spec.update({
            "database_url": "postgresql://prod-server/db",
            "redis_url": "redis://prod-server",
            "cache_ttl": 3600,
        })
    elif env == "staging":
        base_spec.update({
            "database_url": "postgresql://staging-server/db",
            "redis_url": "redis://staging-server",
            "cache_ttl": 600,
        })
    else:  # dev
        base_spec.update({
            "database_url": "postgresql://localhost/dev_db",
            "redis_url": "redis://localhost",
            "cache_ttl": 60,
        })

    # Add wired services
    base_spec.update({
        "psycopg2.connect db": {"dsn": "{database_url}"},
        "redis.Redis cache": {
            "url": "{redis_url}",
            "ttl": "{cache_ttl}",
        },
    })

    return base_spec

# Usage
env = os.getenv("APP_ENV", "dev")
wired = Wiring(get_spec(env), thread_safe=env == "production")
```

## Factory Pattern

Use factory methods for complex object creation:

```python
from apywire import Wiring
from datetime import datetime

spec = {
    # Use factory method to create from timestamp
    "datetime.datetime app_start.fromtimestamp": {
        0: 1704067200,  # Jan 1, 2024
    },

    # Use factory method with ISO format
    "datetime.datetime launch_date.fromisoformat": {
        "date_string": "2024-06-15T12:00:00",
    },

    # Custom factory method
    "myapp.Config config.from_env": {},  # Loads from environment

    # Service using factory-created objects
    "myapp.Scheduler scheduler": {
        "start_time": "{app_start}",
        "config": "{config}",
    },
}

wired = Wiring(spec)
scheduler = wired.scheduler()
```

## Logging Setup

Configure logging infrastructure:

```python
from apywire import Wiring
import logging

spec = {
    # Log level configuration
    "log_level": "INFO",
    "log_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",

    # Logger instances
    "logging.Logger app_logger": {
        "name": "myapp",
    },
    "logging.Logger db_logger": {
        "name": "myapp.database",
    },
    "logging.Logger api_logger": {
        "name": "myapp.api",
    },

    # Services using loggers
    "DatabaseService db_service": {
        "logger": "{db_logger}",
    },
    "APIService api_service": {
        "logger": "{api_logger}",
    },
}

wired = Wiring(spec)

# Configure log levels
app_logger = wired.app_logger()
app_logger.setLevel(logging.INFO)

# Use services with logging
db_service = wired.db_service()
```

## Microservices Communication

Set up clients for microservices:

```python
from apywire import Wiring

spec = {
    # Service endpoints
    "auth_service_url": "https://auth.example.com",
    "user_service_url": "https://users.example.com",
    "payment_service_url": "https://payments.example.com",

    # HTTP clients for each service
    "requests.Session auth_client": {},
    "requests.Session user_client": {},
    "requests.Session payment_client": {},

    # Service wrappers
    "AuthService auth": {
        "base_url": "{auth_service_url}",
        "client": "{auth_client}",
    },
    "UserService users": {
        "base_url": "{user_service_url}",
        "client": "{user_client}",
    },
    "PaymentService payments": {
        "base_url": "{payment_service_url}",
        "client": "{payment_client}",
    },

    # Orchestrator
    "OrderOrchestrator orchestrator": {
        "auth": "{auth}",
        "users": "{users}",
        "payments": "{payments}",
    },
}

wired = Wiring(spec, thread_safe=True)
orchestrator = wired.orchestrator()
```

## File Processing Pipeline

Build a data processing pipeline:

```python
from apywire import Wiring

spec = {
    # Input/output paths
    "input_path": "/data/input",
    "output_path": "/data/output",
    "temp_path": "/data/temp",

    # Path objects
    "pathlib.Path input_dir": ["{input_path}"],
    "pathlib.Path output_dir": ["{output_path}"],
    "pathlib.Path temp_dir": ["{temp_path}"],

    # Pipeline stages
    "FileReader reader": {
        "input_dir": "{input_dir}",
    },
    "DataValidator validator": {},
    "DataTransformer transformer": {
        "temp_dir": "{temp_dir}",
    },
    "DataWriter writer": {
        "output_dir": "{output_dir}",
    },

    # Pipeline
    "ProcessingPipeline pipeline": {
        "reader": "{reader}",
        "validator": "{validator}",
        "transformer": "{transformer}",
        "writer": "{writer}",
    },
}

wired = Wiring(spec)
pipeline = wired.pipeline()
pipeline.run()
```

## Scheduled Tasks

Set up scheduled tasks with dependencies:

```python
from apywire import Wiring
import schedule

spec = {
    # Database connection
    "psycopg2.connect db": {"dsn": "postgresql://localhost/mydb"},

    # Email service
    "EmailService email": {"api_key": "secret"},

    # Task definitions
    "DailyReportTask daily_report": {
        "db": "{db}",
        "email": "{email}",
        "schedule": "00:00",  # Midnight
    },
    "HourlyCleanupTask cleanup": {
        "db": "{db}",
        "schedule": ":00",  # Every hour
    },

    # Scheduler
    "TaskScheduler scheduler": {
        "tasks": ["{daily_report}", "{cleanup}"],
    },
}

wired = Wiring(spec, thread_safe=True)
scheduler = wired.scheduler()

# Schedule tasks
for task in [wired.daily_report(), wired.cleanup()]:
    schedule.every().day.at(task.schedule).do(task.run)

# Run scheduler
while True:
    schedule.run_pending()
    time.sleep(60)
```

## CLI Application

Build a command-line application:

```python
from apywire import Wiring
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="dev")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    spec = {
        "env": args.env,
        "verbose": args.verbose,

        # Configuration
        "Config config": {
            "env": "{env}",
            "verbose": "{verbose}",
        },

        # Services
        "Database db": {"config": "{config}"},
        "Logger logger": {"verbose": "{verbose}"},

        # CLI
        "CLI cli": {
            "db": "{db}",
            "logger": "{logger}",
        },
    }

    wired = Wiring(spec)
    cli = wired.cli()
    cli.run()

if __name__ == "__main__":
    main()
```

## Next Steps

- **[User Guide](user-guide/index.md)** - Detailed documentation
- **[API Reference](api-reference.md)** - Complete API documentation
- **[Development](development.md)** - Contributing guide
