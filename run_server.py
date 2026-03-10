import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    python_exe = Path(sys.executable)
    pythonw_exe = python_exe.with_name("pythonw.exe")
    runner = str(pythonw_exe if pythonw_exe.exists() else python_exe)

    cmd = [runner, str(root / "app.py")]
    kwargs = {"cwd": str(root), "env": os.environ.copy()}

    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    else:
        kwargs["start_new_session"] = True
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL

    process = subprocess.Popen(cmd, **kwargs)
    (root / "server.pid").write_text(str(process.pid), encoding="utf-8")

    print(f"Server started (pid {process.pid}).")
    print("Open http://127.0.0.1:5000")


if __name__ == "__main__":
    main()
