# Architecture

The architecture, the folder map, the business rules and the step-by-step processes are in **[docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md)**
(this file used to hold an older summary that no longer matched the system).

In one line: phones and browsers call one FastAPI backend (`backend/`, on Fly.io); the backend owns all rules and data (PostgreSQL + an S3 bucket);
the web app (`src/`, on Vercel) and the Android app (`mobile/`) are only screens.
