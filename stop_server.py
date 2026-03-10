import os
import signal
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    pid_file = root / "server.pid"
    if not pid_file.exists():
        print("No server.pid found.")
        return

    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        print("Invalid PID file.")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped server (pid {pid}).")
    except ProcessLookupError:
        print("Server process not found.")
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
