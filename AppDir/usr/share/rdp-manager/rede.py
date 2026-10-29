#!/usr/bin/env python3
"""
Funções de rede do RDP Manager: medição de latência até o host e
foco de uma janela de sessão RDP já aberta (via wmctrl/xdotool).
"""

import subprocess
import socket
import time


def medir_latencia_tcp(host, porta=3389, timeout=2.0):
    # Tempo de resposta até a porta RDP do host — não é o "ping" do
    # protocolo RDP em si, mas dá uma noção real e confiável da
    # latência de rede até a máquina, sem depender de nada que o
    # xfreerdp exponha (ele não relata isso pra fora do processo).
    host_real = host
    porta_real = porta

    if ":" in host:
        partes = host.rsplit(":", 1)
        if partes[1].isdigit():
            host_real = partes[0]
            porta_real = int(partes[1])

    inicio = time.monotonic()

    try:
        with socket.create_connection((host_real, porta_real), timeout=timeout):
            pass
        return int((time.monotonic() - inicio) * 1000)
    except Exception:
        return None


def gerar_titulo_janela_rdp(nome_conexao):
    # Título fixo e previsível, usado tanto ao abrir o xfreerdp
    # quanto depois pra localizar essa janela específica.
    return f"RDPManager - {nome_conexao}"


def focar_janela_por_titulo(titulo):
    """
    Tenta trazer pra frente uma janela pelo título, usando wmctrl
    primeiro e xdotool como alternativa (o que estiver disponível no
    sistema — nenhum dos dois precisa estar embutido no AppImage,
    já que o app roda sem sandbox e pode chamar ferramentas do
    sistema normalmente).

    Retorna True se conseguiu, False se nenhuma ferramenta funcionou
    (ou nenhuma das duas está instalada).
    """
    try:
        resultado = subprocess.run(
            ["wmctrl", "-a", titulo],
            capture_output=True,
            timeout=3
        )
        if resultado.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except Exception:
        pass

    try:
        resultado = subprocess.run(
            ["xdotool", "search", "--name", titulo, "windowactivate"],
            capture_output=True,
            timeout=3
        )
        if resultado.returncode == 0:
            return True
    except FileNotFoundError:
        pass
    except Exception:
        pass

    return False
