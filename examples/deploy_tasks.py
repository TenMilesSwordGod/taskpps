from invoke import task


@task
def migrate_db(c, target_version="latest"):
    print(f"Migrating database to version: {target_version}")
    c.run(f"python manage.py migrate --version {target_version}")


@task
def health_check(c, url="http://localhost:8000"):
    print(f"Checking health at {url}")
    result = c.run(f"curl -sf {url}/health", warn=True)
    if result.ok:
        print("Health check passed")
    else:
        print("Health check failed")
        raise SystemExit(1)
