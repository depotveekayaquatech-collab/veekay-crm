# Load test

Throwaway-database load test: 1,500 stores, ~70 employees, 135,000 order entries, 4,000 cash purchases, 2,000 tickets,
3,000 compliance rows and 60,000 audit rows (about 73 MB).

    pip install httpx psutil pillow
    cd backend
    python scripts/loadtest/setup_db.py      # (re)creates the separate database `veekay_load`; never touches your dev data
    python scripts/loadtest/run_server.py    # API on :8010, 2 workers, rate limiting OFF (all virtual users share one IP)
    python scripts/loadtest/load.py          # login emp10 emp25 emp50 mixed search orders upload  (or name some phases)

Run it against a Linux machine that looks like production, with the load generator on a SEPARATE machine. The first
results were taken on one Windows laptop running the API, PostgreSQL and the load generator together, and the same test
varied 3-30x between runs. See docs/load-test/ for those results.
