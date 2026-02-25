⚡ High-Performance Async Job Processing Engineyyy

A production-ready asynchronous job processing engine built with FastAPI, SQLAlchemy, Redis, and PostgreSQL. Features priority queuing, exponential backoff retries, role-based authentication, and a live monitoring dashboard.

## 🚀 Features

- **Async Job Processing** - Non-blocking workers using asyncio
- **Priority Queue** - Redis-backed sorted sets for fast dequeuing
- **Dual-Queue Architecture** - Redis fast path with PostgreSQL fallback
- **Exponential Backoff Retries** - Automatic retries with configurable backoff (2^attempt seconds)
- **Role-Based Access Control** - Admin, Operator, Viewer roles
- **JWT Authentication** - Secure API access with Bearer tokens
- **Live Dashboard** - Real-time monitoring with auto-refresh
- **Bulk Job Creation** - Create up to 100 jobs in a single request
- **Job Scheduling** - Schedule jobs for future execution
- **Atomic Job Claiming** - `FOR UPDATE SKIP LOCKED` prevents duplicate execution

## 📁 Project Structure

```
job_engine/
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app with lifespan
│   ├── config.py            # Pydantic settings
│   ├── database.py          # Async SQLAlchemy setup
│   ├── redis_client.py      # Redis queue implementation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User model with roles
│   │   └── job.py           # Job model with status tracking
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py          # User Pydantic schemas
│   │   └── job.py           # Job Pydantic schemas
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── dependencies.py  # Auth dependencies & role checks
│   │   ├── router.py        # Auth endpoints
│   │   └── utils.py         # Password hashing & JWT
│   ├── api/
│   │   ├── __init__.py
│   │   ├── jobs.py          # Job CRUD endpoints
│   │   └── dashboard.py     # Monitoring dashboard
│   └── workers/
│       ├── __init__.py
│       ├── manager.py       # Worker pool manager
│       ├── executor.py      # Job execution logic
│       └── handlers/
│           ├── __init__.py
│           ├── email_handler.py
│           ├── ai_handler.py
│           └── data_cleaning_handler.py
├── templates/
│   └── dashboard.html       # Live monitoring UI
├── requirements.txt
├── alembic.ini
├── run.py
└── .env.example
```

## 🛠️ Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+

### 1. Start Dependencies

```bash
# Start PostgreSQL
docker run -d --name pg -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=job_engine \
  postgres:16

# Start Redis
docker run -d --name redis -p 6379:6379 redis:7
```

### 2. Install Python Dependencies

```bash
cd job_engine
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your settings (optional)
```

### 4. Run Database Migrations

```bash
# Option A: Use Alembic
alembic upgrade head

# Option B: Auto-create tables (via init_db on startup)
# Tables are created automatically when the app starts
```

### 5. Start the Server

```bash
python run.py
```

The server will start at `http://localhost:8000`. Workers start automatically with the server.

## 📚 API Reference

### Authentication

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | Public | Register new user |
| POST | `/auth/login` | Public | Get JWT token |
| GET | `/auth/users` | Admin | List all users |

### Jobs

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| POST | `/jobs` | Operator+ | Create a job |
| POST | `/jobs/bulk` | Operator+ | Create up to 100 jobs |
| GET | `/jobs` | Viewer+ | List jobs (paginated) |
| GET | `/jobs/stats` | Viewer+ | Get aggregated statistics |
| GET | `/jobs/{id}` | Viewer+ | Get job details |
| POST | `/jobs/{id}/cancel` | Operator+ | Cancel a job |
| POST | `/jobs/{id}/retry` | Operator+ | Retry failed job |

### Monitoring

| Method | Endpoint | Role | Description |
|--------|----------|------|-------------|
| GET | `/dashboard` | Public | Live HTML dashboard |
| GET | `/health` | Public | Health check |

## 🔧 Usage Examples

### Register an Admin User

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@test.com",
    "password": "securepass123",
    "role": "admin"
  }'
```

### Login

```bash
curl -X POST "http://localhost:8000/auth/login?username=admin&password=securepass123"
# Response: {"access_token": "<TOKEN>", "token_type": "bearer"}
```

### Submit an Email Job

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Welcome Email",
    "job_type": "email",
    "priority": 10,
    "payload": {
      "to": "user@example.com",
      "subject": "Welcome!",
      "body": "Hello and welcome!"
    },
    "max_retries": 3
  }'
```

### Submit an AI Task

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sentiment Analysis",
    "job_type": "ai_task",
    "priority": 5,
    "payload": {
      "task": "classification",
      "input": "This product is amazing!"
    }
  }'
```

### Submit a Data Cleaning Job

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Clean Sales Data",
    "job_type": "data_cleaning",
    "priority": 15,
    "payload": {
      "source": "sales_2024.csv",
      "row_count": 50000,
      "operations": ["dedup", "normalize", "validate"]
    }
  }'
```

### Bulk Create Jobs

```bash
curl -X POST http://localhost:8000/jobs/bulk \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "jobs": [
      {"name": "Email 1", "job_type": "email", "payload": {"to": "a@test.com"}},
      {"name": "Email 2", "job_type": "email", "payload": {"to": "b@test.com"}},
      {"name": "Email 3", "job_type": "email", "payload": {"to": "c@test.com"}}
    ]
  }'
```

### View Dashboard

Open `http://localhost:8000/dashboard` in your browser for real-time monitoring.

## ⚙️ Configuration

Environment variables (set in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `USE_REDIS` | `true` | Enable Redis queue (fallback to PostgreSQL if false) |
| `SECRET_KEY` | `your-super-secret-...` | JWT signing key |
| `MAX_WORKERS` | `10` | Maximum concurrent workers |
| `MAX_RETRIES` | `5` | Default max retries per job |
| `RETRY_BACKOFF_BASE` | `2.0` | Exponential backoff base (seconds) |
| `JOB_TIMEOUT_SECONDS` | `300` | Max execution time per job |
| `POLL_INTERVAL_SECONDS` | `1.0` | Queue polling interval |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                       │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ Auth API │  │ Jobs API │  │Dashboard │  │  Health API  │ │
│  │ /auth/*  │  │ /jobs/*  │  │/dashboard│  │  /health     │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────────────┘ │
│       │              │             │                          │
│  ┌────▼──────────────▼─────────────▼───────────────────────┐ │
│  │               Role-Based Auth Layer                      │ │
│  │         ADMIN > OPERATOR > VIEWER                        │ │
│  └──────────────────────┬──────────────────────────────────┘ │
│                         │                                     │
│  ┌──────────────────────▼──────────────────────────────────┐ │
│  │                  Worker Manager                          │ │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                 │ │
│  │  │Worker 1 │  │Worker 2 │  │Worker N │  (Semaphore)     │ │
│  │  └────┬────┘  └────┬────┘  └────┬────┘                 │ │
│  │       └─────────────┼───────────┘                       │ │
│  │                     ▼                                    │ │
│  │              Job Executor                                │ │
│  │    ┌─────────┬──────────┬──────────────┐                │ │
│  │    │  Email  │ AI Task  │ Data Cleaning│                │ │
│  │    │ Handler │ Handler  │   Handler    │                │ │
│  │    └─────────┴──────────┴──────────────┘                │ │
│  │                                                          │ │
│  │    Retry Logic: Exponential Backoff (2^attempt sec)     │ │
│  │    Timeout: Configurable per-job                        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                         │                                     │
│           ┌─────────────┼──────────────┐                     │
│           ▼                            ▼                     │
│   ┌──────────────┐            ┌──────────────┐              │
│   │  PostgreSQL  │            │    Redis     │              │
│   │  - Users     │            │  - Priority  │              │
│   │  - Jobs      │            │    Queue     │              │
│   │  - Results   │            │  - Stats     │              │
│   │  (persistent │            │  - Pub/Sub   │              │
│   │   + locking) │            │  (optional)  │              │
│   └──────────────┘            └──────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

## 🔑 Key Design Decisions

1. **Dual-queue architecture** — Redis provides sub-millisecond priority dequeuing; PostgreSQL serves as a reliable fallback if Redis is unavailable.

2. **Exponential backoff retries** — Failed jobs wait 2^attempt seconds before retrying (2s → 4s → 8s → 16s → 32s), preventing thundering-herd problems.

3. **Concurrency via semaphore** — `asyncio.Semaphore(MAX_WORKERS)` caps concurrent execution without OS threads.

4. **Atomic job claiming** — `FOR UPDATE SKIP LOCKED` ensures no two workers execute the same job.

5. **Role hierarchy** — Simple level-based RBAC: Viewer < Operator < Admin.

## 📝 License

MIT License
y
