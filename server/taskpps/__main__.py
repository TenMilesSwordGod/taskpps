import uvicorn

from taskpps.config import get_settings, load_settings


def main():
    load_settings()
    settings = get_settings()
    uvicorn.run(
        "taskpps.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
