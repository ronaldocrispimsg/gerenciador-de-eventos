"""Script auxiliar para subir os 7 servicos do EventHub localmente em portas distintas."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

SERVICES = [
    ("soa-identidade", "services.soa_identidade.app", 5001),
    ("soa-notificacao", "services.soa_notificacao.app", 5002),
    ("ms-eventos", "services.ms_eventos.app", 5004),
    ("ms-inscricoes", "services.ms_inscricoes.app", 5005),
    ("ms-certificados", "services.ms_certificados.app", 5006),
    ("soa-orquestrador", "services.soa_orquestrador.app", 5003),
    ("api-gateway", "services.api_gateway.app", 5000),
]


def main() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    processes: list[tuple[str, subprocess.Popen[bytes]]] = []

    print("Iniciando os 7 servicos do EventHub (SOA + Microsservicos)...")
    for name, module, port in SERVICES:
        proc = subprocess.Popen([sys.executable, "-m", module], cwd=str(ROOT_DIR), env=env)
        processes.append((name, proc))
        print(f"  [+] {name:<18} rodando na porta {port} (PID {proc.pid})")
        time.sleep(0.2)

    print("\nTodos os servicos ativos! Gateway: http://127.0.0.1:5000/apidocs")
    print("Pressione Ctrl+C para encerrar todos os servicos.")

    def _shutdown(signum: int, frame: object) -> None:
        print("\nEncerrando servicos EventHub...")
        for _, proc in reversed(processes):
            proc.terminate()
        for _, proc in processes:
            proc.wait(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
