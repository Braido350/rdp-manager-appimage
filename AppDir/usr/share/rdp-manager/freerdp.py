#!/usr/bin/env python3
"""
Escolha do executável do FreeRDP.

Prioridade:
  1. xfreerdp instalado no sistema (xfreerdp3 ou xfreerdp), rodando
     com o ambiente original da máquina (sem as libs do AppImage);
  2. xfreerdp embutido no AppImage, como alternativa.

Variável opcional RDPM_FREERDP=embutido força o uso do embutido.
"""

import os
import shutil

_NOMES = ("xfreerdp3", "xfreerdp")


def _dentro_do_appdir(caminho):
    appdir = os.environ.get("RDPM_APPDIR")
    if not appdir:
        return False
    real = os.path.realpath(caminho)
    return real.startswith(os.path.realpath(appdir) + os.sep)


def _procurar_no_sistema():
    path = os.environ.get("RDPM_ORIG_PATH", os.environ.get("PATH", ""))
    for nome in _NOMES:
        achado = shutil.which(nome, path=path)
        if achado and not _dentro_do_appdir(achado):
            return achado
    return None


def _ambiente_sistema():
    """Ambiente sem as bibliotecas/caminhos do AppImage."""
    env = os.environ.copy()
    if "RDPM_ORIG_PATH" in env:
        env["PATH"] = env["RDPM_ORIG_PATH"]
    if "RDPM_ORIG_LD_LIBRARY_PATH" in env:
        original = env["RDPM_ORIG_LD_LIBRARY_PATH"]
        if original:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def resolver_freerdp():
    """Retorna (executavel, env, origem) com origem 'sistema' ou 'embutido'."""
    if os.environ.get("RDPM_FREERDP", "").lower() not in ("embutido", "bundled"):
        sistema = _procurar_no_sistema()
        if sistema:
            return sistema, _ambiente_sistema(), "sistema"

    appdir = os.environ.get("RDPM_APPDIR")
    if appdir:
        embutido = os.path.join(appdir, "usr", "bin", "xfreerdp")
        if os.path.exists(embutido):
            return embutido, os.environ.copy(), "embutido"

    return "xfreerdp", os.environ.copy(), "embutido"


# Nomes públicos (usados pelo instalador/atualizador do FreeRDP)
procurar_no_sistema = _procurar_no_sistema
ambiente_sistema = _ambiente_sistema
