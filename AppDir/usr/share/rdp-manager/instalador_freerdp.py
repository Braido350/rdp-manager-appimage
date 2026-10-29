#!/usr/bin/env python3
"""
Lógica de detecção, instalação e atualização do FreeRDP do sistema
(sem nada de interface — a janela fica em aviso_freerdp.py).

Como funciona:
  * detecta o gerenciador de pacotes da distro (apt, dnf, zypper, pacman);
  * descobre a versão instalada (xfreerdp /version) e a mais recente
    disponível nos repositórios da própria distro;
  * instala/atualiza com `pkexec`, que abre o pedido de senha gráfico
    padrão do sistema (o usuário só digita a senha de administrador).

Tudo roda com o ambiente ORIGINAL da máquina (sem as bibliotecas do
AppImage), senão o gerenciador de pacotes quebraria.
"""

import json
import os
import re
import shutil
import subprocess

from freerdp import procurar_no_sistema, ambiente_sistema
from seguranca import BASE_DIR

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Só oferecemos atualização para FreeRDP gerenciado pelo gerenciador
# de pacotes (em /usr/bin). Um xfreerdp compilado à mão (/usr/local),
# Nix, snap etc. não seria atualizado por ele.
_DIRS_GERENCIADOS = ("/usr/bin", "/bin", "/usr/sbin")


# ============================================================
# CONFIGURAÇÃO (preferências do aviso)
# ============================================================

def ler_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def salvar_config(**valores):
    dados = ler_config()
    dados.update(valores)
    try:
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2)
        os.replace(tmp, CONFIG_FILE)
    except OSError:
        pass  # preferência é só conveniência; não derruba o app


# ============================================================
# VERSÕES
# ============================================================

def parse_versao(texto):
    """'1:2.11.7+dfsg1-1' -> (2, 11, 7). None se não achar."""
    if not texto:
        return None
    texto = re.sub(r"^\d+:", "", texto.strip())          # epoch do apt/rpm
    m = re.search(r"(\d+(?:\.\d+)+)", texto)
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split("."))


def formatar_versao(versao):
    return ".".join(str(p) for p in versao) if versao else "?"


def _rodar(cmd, timeout=30):
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, env=ambiente_sistema(),
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception:
        return 1, ""


def versao_instalada(exe):
    """Versão do xfreerdp informado, ou None."""
    for arg in ("/version", "--version"):
        _, saida = _rodar([exe, arg], timeout=10)
        m = re.search(r"version\s+(\d+(?:\.\d+)+)", saida, re.I)
        if m:
            return parse_versao(m.group(1))
    return None


# ============================================================
# GERENCIADOR DE PACOTES
# ============================================================

def _existe(cmd):
    path = os.environ.get("RDPM_ORIG_PATH", os.environ.get("PATH", ""))
    return shutil.which(cmd, path=path) is not None


def detectar_gerenciador():
    """'apt' | 'dnf' | 'zypper' | 'pacman' | None (não suportado)."""
    # Sistemas imutáveis (Silverblue/Kinoite...): dnf não instala nada.
    if os.path.exists("/run/ostree-booted"):
        return None
    for nome, binario in (
        ("apt", "apt-get"), ("dnf", "dnf"),
        ("zypper", "zypper"), ("pacman", "pacman"),
    ):
        if _existe(binario):
            return nome
    return None


def pacote_alvo(gerenciador):
    """Nome do pacote do cliente X11 do FreeRDP nessa distro."""
    if gerenciador == "apt":
        # Prefere a série 3.x; cai para a 2.x em distros mais antigas.
        if _candidata_apt("freerdp3-x11"):
            return "freerdp3-x11"
        return "freerdp2-x11"
    return "freerdp"


def _candidata_apt(pacote):
    _, saida = _rodar(["apt-cache", "policy", pacote], timeout=20)
    m = re.search(r"Candidate:\s*(\S+)", saida)
    if not m or m.group(1) == "(none)":
        return None
    return parse_versao(m.group(1))


def versao_candidata(gerenciador, pacote):
    """Versão mais recente disponível nos repositórios (ou None)."""
    if gerenciador == "apt":
        return _candidata_apt(pacote)

    if gerenciador == "dnf":
        _, saida = _rodar(
            ["dnf", "-q", "repoquery", "--latest-limit=1",
             "--queryformat", "%{version}\n", pacote],
            timeout=120,
        )
        versoes = [parse_versao(l) for l in saida.splitlines()]
        versoes = [v for v in versoes if v]
        return max(versoes) if versoes else None

    if gerenciador == "zypper":
        _, saida = _rodar(
            ["zypper", "--non-interactive", "--quiet", "info", pacote],
            timeout=120,
        )
        m = re.search(r"^Version\s*:\s*(\S+)", saida, re.M)
        return parse_versao(m.group(1)) if m else None

    if gerenciador == "pacman":
        _, saida = _rodar(["pacman", "-Si", pacote], timeout=30)
        m = re.search(r"^Version\s*:\s*(\S+)", saida, re.M)
        return parse_versao(m.group(1)) if m else None

    return None


# ============================================================
# DIAGNÓSTICO
# ============================================================

def diagnosticar():
    """
    Retorna um dict com:
      estado: 'ausente' | 'desatualizado' | 'ok' | 'indeterminado'
      exe, instalada, candidata, gerenciador, pacote
    """
    ger = detectar_gerenciador()
    pacote = pacote_alvo(ger) if ger else None
    exe = procurar_no_sistema()

    info = {
        "estado": "indeterminado", "exe": exe, "instalada": None,
        "candidata": None, "gerenciador": ger, "pacote": pacote,
    }

    if not exe:
        info["estado"] = "ausente"
        return info

    info["instalada"] = versao_instalada(exe)

    if not ger or not os.path.dirname(exe) in _DIRS_GERENCIADOS:
        info["estado"] = "ok"   # não dá pra atualizar automaticamente
        return info

    info["candidata"] = versao_candidata(ger, pacote)

    if (info["instalada"] and info["candidata"]
            and info["candidata"] > info["instalada"]):
        info["estado"] = "desatualizado"
    else:
        info["estado"] = "ok"
    return info


# ============================================================
# INSTALAÇÃO / ATUALIZAÇÃO
# ============================================================

def _script_root(gerenciador, pacote, atualizar):
    """Script executado como administrador (via pkexec)."""
    if gerenciador == "apt":
        return (
            "export DEBIAN_FRONTEND=noninteractive; "
            "apt-get update; "
            f"apt-get install -y {pacote}"
        )
    if gerenciador == "dnf":
        acao = "upgrade" if atualizar else "install"
        return f"dnf {acao} -y {pacote}"
    if gerenciador == "zypper":
        return f"zypper --non-interactive install {pacote}"
    if gerenciador == "pacman":
        return f"pacman -S --noconfirm {pacote}"
    return None


def comando_manual(gerenciador, pacote, atualizar):
    """Comando equivalente, para mostrar ao usuário se o automático falhar."""
    script = _script_root(gerenciador, pacote, atualizar)
    if not script:
        return "Instale o pacote 'freerdp' pelo gerenciador de pacotes da sua distribuição."
    return "sudo sh -c '" + script.replace("export DEBIAN_FRONTEND=noninteractive; ", "") + "'"


def tem_pkexec():
    return _existe("pkexec")


def iniciar_instalacao(gerenciador, pacote, atualizar):
    """
    Dispara a instalação/atualização e devolve o Popen (stdout mesclado
    com stderr, para o chamador acompanhar o progresso).
    Levanta FileNotFoundError se o pkexec não existir.
    """
    script = _script_root(gerenciador, pacote, atualizar)
    cmd = ["pkexec", "/bin/sh", "-c", script]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=ambiente_sistema(),
    )


def traduzir_codigo_saida(codigo):
    """Mensagem amigável para códigos conhecidos do pkexec."""
    if codigo == 126:
        return "A autorização foi cancelada."
    if codigo == 127:
        return ("Não foi possível pedir a senha de administrador "
                "(autenticação falhou ou não há agente de senha ativo).")
    return None
