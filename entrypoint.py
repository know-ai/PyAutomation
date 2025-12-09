import os
import sys
import subprocess

def main():
    # Environment variables with defaults
    cert_file = os.environ.get("CERT_FILE", "")
    key_file = os.environ.get("KEY_FILE", "")
    worker_connections = os.environ.get("WORKER_CONNECTIONS", "100")
    workers = os.environ.get("WORKERS", "1")
    threads = os.environ.get("THREADS", "10")
    port = os.environ.get("PORT", "8050")

    # Base command
    # We use python -m gunicorn to ensure it works even if the binary isn't in PATH
    cmd = [
        "python", "-m", "gunicorn",
        "-c", "gunicorn.conf.py",
        "-k", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker",
        "-w", workers,
        "--worker-connections", worker_connections,
        "--threads", threads,
        "-b", f"0.0.0.0:{port}",
        "wsgi:server"
    ]

    # SSL Configuration Logic
    use_ssl = False
    if os.path.exists(cert_file):
        print(f"\033[36m[INFO]\033[m - Reading {cert_file} file")
        print(f"\033[32m[OK]\033[m - {cert_file} Readed")
        
        if os.path.exists(key_file):
            print(f"\033[36m[INFO]\033[m - Reading {key_file} file")
            print(f"\033[32m[OK]\033[m - {key_file} Readed")
            
            # Add SSL arguments
            cmd.insert(3, f"--keyfile={key_file}")
            cmd.insert(3, f"--certfile={cert_file}")
            use_ssl = True
        else:
            print(f"\033[33m[WARNING]\033[m - {key_file} Not Found service without SSL Certificate")
    else:
        print(f"\033[33m[WARNING]\033[m - {cert_file} Not Found service without SSL Certificate")

    print(f"\033[32m[OK]\033[m - Worker connections: {worker_connections}")
    print(f"\033[32m[OK]\033[m - Number of workers: {workers}")

    # Replace current process with gunicorn
    # Using sys.stdout.flush() to ensure logs appear before exec
    sys.stdout.flush()
    os.execvp(cmd[0], cmd)

if __name__ == "__main__":
    main()

