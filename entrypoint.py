import os
import sys
import subprocess

def main():
    # Environment variables with defaults
    # Usar AUTOMATION_CERT_FILE y AUTOMATION_KEY_FILE para consistencia
    # Si están vacíos, intentar con CERT_FILE y KEY_FILE para compatibilidad hacia atrás
    cert_file_env = os.environ.get("AUTOMATION_CERT_FILE", "") or os.environ.get("CERT_FILE", "")
    key_file_env = os.environ.get("AUTOMATION_KEY_FILE", "") or os.environ.get("KEY_FILE", "")
    
    # Si es una ruta completa (empieza con /), usarla directamente
    # Si es solo un nombre de archivo, construir la ruta en /app/ssl/
    if cert_file_env:
        if cert_file_env.startswith("/"):
            cert_file = cert_file_env
        else:
            cert_file = os.path.join("/app", "ssl", cert_file_env)
    else:
        cert_file = ""
    
    if key_file_env:
        if key_file_env.startswith("/"):
            key_file = key_file_env
        else:
            key_file = os.path.join("/app", "ssl", key_file_env)
    else:
        key_file = ""
    
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

