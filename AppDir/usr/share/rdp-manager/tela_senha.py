#!/usr/bin/env python3
"""
Tela de senha-mestra: criação do cofre no primeiro uso (com migração
automática de instalações antigas sem criptografia) e desbloqueio
nas aberturas seguintes.
"""

import os
import json
from gi.repository import Gtk, GLib

from seguranca import (
    DB_FILE,
    ASSINATURA,
    SenhaInvalida,
    carregar_conexoes,
    salvar_conexoes,
)
from estilo import aplicar_css_moderno
from janela_principal import RDPManager


class TelaSenha(Gtk.ApplicationWindow):

    def __init__(self, app):

        super().__init__(
            application=app,
            title="RDP Manager"
        )

        self.app = app

        self.arquivo_legado = self._detectar_arquivo_legado()
        self.primeiro_uso = self.arquivo_legado is not None or not os.path.exists(DB_FILE)

        self.set_default_size(400, 1)
        self.set_resizable(False)
        self.set_deletable(True)

        # Barra de título explícita, só com minimizar e fechar. Evita
        # botões duplicados/estranhos quando o tema (ex.: KDE) mistura
        # o layout de botões do sistema com o da janela fixa.
        barra = Gtk.HeaderBar()
        barra.set_show_title_buttons(True)
        barra.set_decoration_layout(":minimize,close")
        self.set_titlebar(barra)

        aplicar_css_moderno()

        caixa = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14
        )
        caixa.set_margin_top(36)
        caixa.set_margin_bottom(36)
        caixa.set_margin_start(36)
        caixa.set_margin_end(36)
        self.set_child(caixa)

        icone = Gtk.Image.new_from_icon_name("dialog-password-symbolic")
        icone.set_pixel_size(40)
        icone.set_halign(Gtk.Align.CENTER)
        caixa.append(icone)

        titulo = Gtk.Label()
        titulo.add_css_class("rdp-titulo")
        titulo.set_justify(Gtk.Justification.CENTER)

        if self.primeiro_uso:
            titulo.set_markup("<b>Criar senha-mestra</b>")
        else:
            titulo.set_markup("<b>Cofre bloqueado</b>")

        caixa.append(titulo)

        if self.primeiro_uso:
            if self.arquivo_legado is not None:
                explicacao = Gtk.Label(
                    label=(
                        f"Encontramos {len(self.arquivo_legado)} conexão(ões) "
                        "salva(s) sem criptografia. Crie uma senha-mestra "
                        "para protegê-las a partir de agora. Não existe "
                        "recuperação: se você esquecer essa senha, os "
                        "dados ficam inacessíveis."
                    )
                )
            else:
                explicacao = Gtk.Label(
                    label=(
                        "Suas conexões e senhas vão ficar criptografadas. "
                        "Não existe recuperação: se você esquecer essa "
                        "senha, os dados salvos ficam inacessíveis."
                    )
                )
        else:
            explicacao = Gtk.Label(
                label="Digite a senha-mestra para abrir suas conexões."
            )

        explicacao.add_css_class("dim-label")
        explicacao.set_wrap(True)
        explicacao.set_justify(Gtk.Justification.CENTER)
        explicacao.set_max_width_chars(40)
        caixa.append(explicacao)

        self.campo_senha = Gtk.PasswordEntry()
        self.campo_senha.set_show_peek_icon(True)
        self.campo_senha.set_property("placeholder-text", "Senha-mestra")
        self.campo_senha.connect("activate", self.tentar)
        caixa.append(self.campo_senha)

        if self.primeiro_uso:
            self.campo_confirmar = Gtk.PasswordEntry()
            self.campo_confirmar.set_show_peek_icon(True)
            self.campo_confirmar.set_property("placeholder-text", "Confirme a senha")
            self.campo_confirmar.connect("activate", self.tentar)
            caixa.append(self.campo_confirmar)
        else:
            self.campo_confirmar = None

        self.label_erro = Gtk.Label()
        self.label_erro.add_css_class("error")
        self.label_erro.set_wrap(True)
        self.label_erro.set_visible(False)
        caixa.append(self.label_erro)

        botao = Gtk.Button(
            label="Criar cofre" if self.primeiro_uso else "Desbloquear"
        )
        botao.add_css_class("suggested-action")
        botao.connect("clicked", self.tentar)
        caixa.append(botao)

        self.campo_senha.grab_focus()

    def _detectar_arquivo_legado(self):
        # Versões antigas do RDP Manager gravavam o connections.json
        # em JSON puro, sem criptografia. Se encontrarmos esse
        # formato, tratamos como "primeiro uso" (precisa criar senha
        # -mestra), mas migrando o conteúdo em vez de começar vazio.
        if not os.path.exists(DB_FILE):
            return None

        try:
            with open(DB_FILE, "rb") as arquivo:
                blob = arquivo.read()
        except Exception:
            return None

        if blob.startswith(ASSINATURA):
            return None  # já está no formato criptografado atual

        try:
            dados = json.loads(blob.decode("utf-8"))
            if isinstance(dados, list):
                return dados
        except Exception:
            pass

        return None

    def mostrar_erro(self, texto):
        self.label_erro.set_text(texto)
        self.label_erro.set_visible(True)

    def tentar(self, *_):

        senha = self.campo_senha.get_text()

        if not senha:
            self.mostrar_erro("Digite uma senha.")
            return

        if self.primeiro_uso:

            if len(senha) < 4:
                self.mostrar_erro(
                    "Use uma senha com pelo menos 4 caracteres."
                )
                return

            confirmar = self.campo_confirmar.get_text()

            if senha != confirmar:
                self.mostrar_erro("As senhas não coincidem.")
                return

            salvar_conexoes(self.arquivo_legado or [], senha)

        else:

            try:
                carregar_conexoes(senha)
            except SenhaInvalida:
                self.mostrar_erro("Senha incorreta. Tente de novo.")
                self.campo_senha.set_text("")
                self.campo_senha.grab_focus()
                return
            except Exception as erro:
                self.mostrar_erro(f"Não foi possível abrir o cofre: {erro}")
                return

        janela = RDPManager(self.app, senha)
        janela.present()
        self.destroy()

