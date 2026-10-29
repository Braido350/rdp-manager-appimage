#!/usr/bin/env python3
"""
Janelas de aviso/instalação/atualização do FreeRDP.

Fluxo:
  1. ao abrir o app, verifica em segundo plano (sem travar a tela);
  2. se não há FreeRDP no sistema -> oferece instalar;
     se há uma versão mais nova disponível -> oferece atualizar;
  3. o botão faz tudo sozinho: pede a senha de administrador (janela
     padrão do sistema), instala e avisa quando terminou.
"""

import os
import threading

from gi.repository import Gtk, GLib

import instalador_freerdp as inst


class AvisoFreeRDP:

    def __init__(self, janela_pai):
        self.pai = janela_pai
        self.ocupado = False   # já existe verificação/instalação em curso

    # --------------------------------------------------------
    # ENTRADAS
    # --------------------------------------------------------

    def verificar_na_entrada(self):
        """Chamada ao abrir o app: só aparece se houver algo a fazer."""
        if os.environ.get("RDPM_FREERDP", "").lower() in ("embutido", "bundled"):
            return
        self._verificar(manual=False)

    def verificar_manual(self):
        """Botão da barra: também informa quando está tudo em dia."""
        self._verificar(manual=True)

    # --------------------------------------------------------
    # VERIFICAÇÃO (thread) -> RESULTADO (interface)
    # --------------------------------------------------------

    def _verificar(self, manual):
        if self.ocupado:
            return
        self.ocupado = True

        def trabalho():
            try:
                diag = inst.diagnosticar()
            except Exception:
                diag = {"estado": "indeterminado"}
            GLib.idle_add(self._resultado, diag, manual)

        threading.Thread(target=trabalho, daemon=True).start()

    def _resultado(self, diag, manual):
        self.ocupado = False
        estado = diag["estado"]
        cfg = inst.ler_config()

        if estado == "ausente":
            if not manual and cfg.get("freerdp_nao_perguntar_ausente"):
                return False
            self._aviso_ausente(diag)

        elif estado == "desatualizado":
            nova = inst.formatar_versao(diag["candidata"])
            if not manual and cfg.get("freerdp_versao_ignorada") == nova:
                return False
            self._aviso_atualizar(diag)

        elif manual:
            if estado == "ok":
                self._mensagem(
                    "FreeRDP em dia",
                    "O FreeRDP instalado na máquina "
                    f"(versão {inst.formatar_versao(diag['instalada'])}) "
                    "já é a mais recente disponível nos repositórios da sua "
                    "distribuição. O RDP Manager está usando ele."
                )
            else:
                self._mensagem(
                    "FreeRDP",
                    "Não consegui verificar o FreeRDP agora. Confira a "
                    "conexão com a internet e tente de novo."
                )
        return False

    # --------------------------------------------------------
    # AVISOS
    # --------------------------------------------------------

    def _aviso_ausente(self, diag):
        suportado = diag["gerenciador"] is not None
        texto = (
            "Não foi identificada nenhuma instalação do FreeRDP na "
            "máquina.\n\nSe quiser uma experiência mais completa e melhor "
            "performance, instale o aplicativo."
        )
        if not suportado:
            texto += (
                "\n\nNão consegui instalar automaticamente nesta "
                "distribuição. Instale o pacote \"freerdp\" pelo gerenciador "
                "de pacotes dela; o RDP Manager passa a usá-lo sozinho."
            )
        self._janela_aviso(
            titulo="FreeRDP não encontrado",
            texto=texto,
            rotulo_acao="Instalar o FreeRDP mais recente" if suportado else None,
            acao=lambda: self._executar(diag, atualizar=False),
            rotulo_ignorar="Não perguntar novamente",
            ao_ignorar=lambda: inst.salvar_config(
                freerdp_nao_perguntar_ausente=True
            ),
        )

    def _aviso_atualizar(self, diag):
        antiga = inst.formatar_versao(diag["instalada"])
        nova = inst.formatar_versao(diag["candidata"])
        self._janela_aviso(
            titulo="Atualização do FreeRDP",
            texto=(
                "Foi identificado que o FreeRDP tem uma atualização mais "
                f"recente.\n\nInstalada: {antiga}\nDisponível: {nova}\n\n"
                "Deseja atualizar?"
            ),
            rotulo_acao="Atualizar",
            acao=lambda: self._executar(diag, atualizar=True),
            rotulo_ignorar="Ignorar esta versão",
            ao_ignorar=lambda: inst.salvar_config(freerdp_versao_ignorada=nova),
        )

    def _janela_aviso(self, titulo, texto, rotulo_acao, acao,
                      rotulo_ignorar, ao_ignorar):
        janela = Gtk.Window()
        janela.set_title(titulo)
        janela.set_transient_for(self.pai)
        janela.set_modal(True)
        janela.set_default_size(460, 240)

        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for lado in ("top", "bottom", "start", "end"):
            getattr(caixa, f"set_margin_{lado}")(18)
        janela.set_child(caixa)

        t = Gtk.Label()
        t.set_markup(f"<big><b>{GLib.markup_escape_text(titulo)}</b></big>")
        t.set_halign(Gtk.Align.START)
        caixa.append(t)

        corpo = Gtk.Label(label=texto)
        corpo.set_wrap(True)
        corpo.set_xalign(0)
        corpo.set_halign(Gtk.Align.START)
        corpo.set_vexpand(True)
        corpo.set_valign(Gtk.Align.START)
        caixa.append(corpo)

        botoes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        botoes.set_halign(Gtk.Align.END)
        caixa.append(botoes)

        b_ignorar = Gtk.Button(label=rotulo_ignorar)
        b_ignorar.add_css_class("flat")
        b_ignorar.connect(
            "clicked", lambda b: (ao_ignorar(), janela.close())
        )
        botoes.append(b_ignorar)

        b_depois = Gtk.Button(label="Agora não" if rotulo_acao else "OK")
        b_depois.connect("clicked", lambda b: janela.close())
        botoes.append(b_depois)

        if rotulo_acao:
            b_acao = Gtk.Button(label=rotulo_acao)
            b_acao.add_css_class("suggested-action")

            def clicou(_b):
                janela.close()
                acao()

            b_acao.connect("clicked", clicou)
            botoes.append(b_acao)
            janela.set_default_widget(b_acao)

        janela.present()

    # --------------------------------------------------------
    # INSTALAÇÃO / ATUALIZAÇÃO
    # --------------------------------------------------------

    def _executar(self, diag, atualizar):
        if self.ocupado:
            return
        ger, pacote = diag["gerenciador"], diag["pacote"]
        verbo = "Atualizando" if atualizar else "Instalando"

        if not inst.tem_pkexec():
            self._mensagem_falha(
                "Não encontrei o componente que pede a senha de "
                "administrador (pkexec).",
                ger, pacote, atualizar, ""
            )
            return

        self.ocupado = True

        # Janela de progresso: sem botão de fechar enquanto roda.
        janela = Gtk.Window()
        janela.set_title(f"{verbo} o FreeRDP")
        janela.set_transient_for(self.pai)
        janela.set_modal(True)
        janela.set_deletable(False)
        janela.set_default_size(420, 150)

        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for lado in ("top", "bottom", "start", "end"):
            getattr(caixa, f"set_margin_{lado}")(18)
        janela.set_child(caixa)

        linha = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        spinner = Gtk.Spinner()
        spinner.start()
        linha.append(spinner)
        titulo = Gtk.Label()
        titulo.set_markup(f"<b>{verbo} o FreeRDP…</b>")
        linha.append(titulo)
        caixa.append(linha)

        status = Gtk.Label(
            label="Digite a senha de administrador quando o sistema pedir."
        )
        status.set_wrap(True)
        status.set_xalign(0)
        status.set_halign(Gtk.Align.START)
        status.set_max_width_chars(48)
        caixa.append(status)
        janela.present()

        def atualizar_status(txt):
            status.set_label(txt[:120])
            return False

        def trabalho():
            ultimas = []
            try:
                proc = inst.iniciar_instalacao(ger, pacote, atualizar)
                for l in proc.stdout:
                    l = l.rstrip()
                    if l:
                        ultimas.append(l)
                        ultimas = ultimas[-40:]
                        GLib.idle_add(atualizar_status, l)
                codigo = proc.wait()
            except Exception as erro:
                codigo, ultimas = 1, [str(erro)]
            GLib.idle_add(terminou, codigo, "\n".join(ultimas))

        def terminou(codigo, log):
            spinner.stop()
            janela.set_deletable(True)
            janela.close()
            self.ocupado = False

            nova = None
            exe = inst.procurar_no_sistema()
            if exe:
                nova = inst.versao_instalada(exe)

            if codigo == 0 and exe:
                inst.salvar_config(freerdp_nao_perguntar_ausente=False)
                self._mensagem(
                    "Pronto!",
                    ("FreeRDP atualizado" if atualizar else "FreeRDP instalado")
                    + f" com sucesso (versão {inst.formatar_versao(nova)}).\n\n"
                    "As próximas conexões já vão usar ele — não precisa "
                    "reiniciar o app."
                )
            else:
                motivo = inst.traduzir_codigo_saida(codigo)
                self._mensagem_falha(motivo, ger, pacote, atualizar, log)
            return False

        threading.Thread(target=trabalho, daemon=True).start()

    # --------------------------------------------------------
    # MENSAGENS
    # --------------------------------------------------------

    def _mensagem_falha(self, motivo, ger, pacote, atualizar, log):
        partes = [motivo or "A instalação não foi concluída."]
        if motivo is None and log:
            partes.append("Detalhes:\n" + "\n".join(log.splitlines()[-8:]))
        partes.append(
            "Se preferir, rode no terminal:\n"
            + inst.comando_manual(ger, pacote, atualizar)
        )
        self._mensagem("Não foi possível concluir", "\n\n".join(partes))

    def _mensagem(self, titulo, texto):
        # Reaproveita o diálogo padrão do app (pequeno e sempre fechável)
        self.pai.mostrar_dialogo_mensagem(titulo, texto)
