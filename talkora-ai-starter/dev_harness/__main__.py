"""Loopback-only launcher; refuses production and known application ports."""
import argparse
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--port", type=int, default=18082)
    args = parser.parse_args()
    if not 18000 <= args.port <= 18999:
        parser.error("Use a separate development port in 18000..18999")
    uvicorn.run("dev_harness.app:create_app", factory=True, host="127.0.0.1", port=args.port,
                access_log=False, log_level="warning")
