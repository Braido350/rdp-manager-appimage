#!/usr/bin/env python3
"""
Ponto de entrada do RDP Manager.

Responsabilidades ficam divididas em módulos:
  seguranca.py        -> criptografia e leitura/gravação do cofre
  estilo.py            -> CSS e tema
  rede.py               -> latência e foco de janela do xfreerdp
  tela_senha.py         -> tela de criação/desbloqueio do cofre
  janela_principal.py   -> janela principal (RDPManager)
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from seguranca import CRYPTO_DISPONIVEL
from tela_senha import TelaSenha


class Aplicacao(Gtk.Application):

    def __init__(self):

        super().__init__(
            application_id="br.com.rdpmanager",
            flags=0
        )


    def do_activate(self):

        # Já desbloqueado e rodando em segundo plano? Só mostra de novo
        # a janela principal (sem pedir a senha-mestra outra vez).
        principal = getattr(self, "janela_principal", None)
        if principal is not None:
            principal.set_visible(True)
            principal.present()
            return

        janela = self.props.active_window

        if janela is None:

            if not CRYPTO_DISPONIVEL:
                self._erro_sem_criptografia()
                return

            janela = TelaSenha(self)

        janela.present()

    def _erro_sem_criptografia(self):
        dialogo = Gtk.MessageDialog(
            application=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Biblioteca de criptografia não encontrada",
            secondary_text=(
                "O RDP Manager precisa do pacote 'cryptography' do "
                "Python pra proteger suas conexões com senha-mestra. "
                "Instale-o (ex.: python3-cryptography) e abra o app "
                "de novo."
            ),
        )
        dialogo.connect("response", lambda d, r: self.quit())
        dialogo.present()


# ============================================================
# MAIN
# ============================================================

app = Aplicacao()

app.run()
