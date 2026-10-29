#!/usr/bin/env python3
"""
Janela principal do RDP Manager: cadastro/edição/exclusão de
conexões, lista de conexões salvas, execução do xfreerdp, status de
conexões ativas (com ping em segundo plano) e import/export de
backup criptografado.
"""

import os
import json
import subprocess
import tempfile
import threading
from datetime import datetime
from gi.repository import Gtk, GLib, Gdk, Gio

from seguranca import (
    DB_FILE,
    ASSINATURA,
    SenhaInvalida,
    carregar_conexoes,
    salvar_conexoes,
    validar_conexao,
    criptografar_bytes,
    descriptografar_bytes,
)
from estilo import aplicar_css_moderno
from freerdp import resolver_freerdp
from aviso_freerdp import AvisoFreeRDP
from rede import (
    medir_latencia_tcp,
    gerar_titulo_janela_rdp,
    focar_janela_por_titulo,
)


class RDPManager(Gtk.ApplicationWindow):

    def __init__(self, app, senha_mestra):

        self.senha_mestra = senha_mestra

        super().__init__(
            application=app,
            title="RDP Manager"
        )

        self.conexoes = carregar_conexoes(self.senha_mestra)
        self.texto_filtro = ""
        self.conectando = False
        self.editando_nome = None  # nome da conexão sendo editada
        self.processos_ativos = {}  # nome_da_conexao -> subprocess.Popen
        self.pings = {}  # nome_da_conexao -> latência em ms (ou None)
        self.labels_ping = {}  # nome_da_conexao -> Gtk.Label (badge "Conectado · Xms")

        aplicar_css_moderno()

        self.set_default_size(460, 600)

        # Fechar a janela (X) só ESCONDE: o app continua em segundo
        # plano com o cofre aberto, então não pede a senha de novo.
        # Para voltar, é só abrir o RDP Manager outra vez (atalho do
        # menu/AppImage). Não há opção de encerrar pela interface.
        self._app = app
        app.hold()
        app.janela_principal = self
        self.connect("close-request", self._ao_fechar)

        self.criar_interface()
        self.atualizar_lista()

        # Mede a latência das conexões ativas a cada 4 segundos,
        # em segundo plano (sem travar a interface).
        GLib.timeout_add_seconds(4, self._tick_pings)

        # Verifica se o FreeRDP do sistema está instalado/atualizado
        # (em segundo plano; só mostra aviso se houver algo a fazer).
        self.aviso_freerdp = AvisoFreeRDP(self)
        GLib.timeout_add(
            1500, lambda: (self.aviso_freerdp.verificar_na_entrada(), False)[1]
        )


    # ========================================================
    # SEGUNDO PLANO
    # ========================================================

    def _ao_fechar(self, janela):
        self.set_visible(False)
        return True   # impede a destruição da janela


    # ========================================================
    # INTERFACE
    # ========================================================

    def criar_interface(self):

        # ====================================================
        # BARRA DE TÍTULO (HeaderBar)
        # ====================================================

        header = Gtk.HeaderBar()
        header.set_show_title_buttons(True)

        titulo_header = Gtk.Label()
        titulo_header.set_markup("<b>RDP Manager</b>")
        header.set_title_widget(titulo_header)

        importar_button = Gtk.Button()
        importar_button.set_icon_name("document-open-symbolic")
        importar_button.set_tooltip_text(
            "Importar backup (.json)"
        )
        importar_button.connect(
            "clicked",
            self.importar_backup
        )
        header.pack_start(importar_button)

        exportar_button = Gtk.Button()
        exportar_button.set_icon_name("document-save-symbolic")
        exportar_button.set_tooltip_text(
            "Exportar backup (.json)"
        )
        exportar_button.connect(
            "clicked",
            self.exportar_backup
        )
        header.pack_start(exportar_button)

        nova_button = Gtk.Button()
        nova_button.set_icon_name("list-add-symbolic")
        nova_button.set_tooltip_text("Nova conexão")
        nova_button.add_css_class("suggested-action")
        nova_button.connect("clicked", self.abrir_formulario_nova)
        header.pack_end(nova_button)

        freerdp_button = Gtk.Button()
        freerdp_button.set_icon_name("software-update-available-symbolic")
        freerdp_button.set_tooltip_text(
            "Verificar / atualizar o FreeRDP"
        )
        freerdp_button.connect(
            "clicked",
            lambda b: self.aviso_freerdp.verificar_manual()
        )
        header.pack_end(freerdp_button)

        self.set_titlebar(header)


        # Formulário de conexão: janela separada, aberta pelo
        # botão "Nova conexão" ou pelo "Editar".
        self.janela_form = Gtk.Window(
            transient_for=self,
            modal=True,
            title="Nova conexão",
            hide_on_close=True
        )
        self.janela_form.set_default_size(360, -1)
        self.janela_form.set_resizable(False)
        self.janela_form.connect(
            "close-request",
            lambda w: (self.limpar_formulario(), False)[1]
        )


        # ====================================================
        # FORMULÁRIO
        # ====================================================

        esquerda = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=15
        )

        esquerda.set_margin_top(25)
        esquerda.set_margin_bottom(25)
        esquerda.set_margin_start(25)
        esquerda.set_margin_end(25)

        self.janela_form.set_child(esquerda)


        descricao = Gtk.Label(
            label="Preencha os dados do computador remoto."
        )
        descricao.add_css_class("dim-label")

        descricao.set_halign(Gtk.Align.START)
        descricao.set_wrap(True)

        esquerda.append(descricao)


        # Nome
        esquerda.append(
            self.criar_label("Nome da conexão")
        )

        self.nome_entry = Gtk.Entry()
        self.nome_entry.set_placeholder_text(
            "Ex: Servidor Prefeitura"
        )

        esquerda.append(self.nome_entry)


        # IP
        esquerda.append(
            self.criar_label("IP / Host")
        )

        self.host_entry = Gtk.Entry()
        self.host_entry.set_placeholder_text(
            "Ex: 192.168.1.100"
        )

        esquerda.append(self.host_entry)


        # Usuário
        esquerda.append(
            self.criar_label("Usuário")
        )

        self.usuario_entry = Gtk.Entry()
        self.usuario_entry.set_placeholder_text(
            "Ex: administrador"
        )

        esquerda.append(self.usuario_entry)


        # Senha
        esquerda.append(
            self.criar_label("Senha")
        )

        self.senha_entry = Gtk.PasswordEntry()
        self.senha_entry.set_show_peek_icon(True)

        esquerda.append(self.senha_entry)


        # Espaçamento
        esquerda.append(
            Gtk.Separator(
                orientation=Gtk.Orientation.HORIZONTAL
            )
        )


        # Botão salvar
        self.salvar_button = Gtk.Button(
            label="Salvar conexão"
        )

        self.salvar_button.add_css_class("suggested-action")

        self.salvar_button.connect(
            "clicked",
            self.salvar_conexao
        )

        esquerda.append(self.salvar_button)


        # Botão cancelar
        limpar_button = Gtk.Button(
            label="Cancelar"
        )

        limpar_button.connect(
            "clicked",
            lambda b: self.janela_form.close()
        )

        esquerda.append(limpar_button)


        # Botão excluir (visível apenas ao editar)
        self.excluir_button = Gtk.Button(
            label="Excluir conexão"
        )

        self.excluir_button.add_css_class(
            "destructive-action"
        )

        self.excluir_button.connect(
            "clicked",
            self.excluir_selecionada
        )

        self.excluir_button.set_visible(False)

        esquerda.append(self.excluir_button)


        # ====================================================
        # LADO DIREITO
        # ====================================================

        direita = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10
        )

        direita.set_margin_top(25)
        direita.set_margin_bottom(25)
        direita.set_margin_start(25)
        direita.set_margin_end(25)

        self.set_child(direita)


        titulo_lista = Gtk.Label()
        titulo_lista.set_markup(
            "<big><b>Conexões salvas</b></big>"
        )
        titulo_lista.add_css_class("rdp-titulo")

        titulo_lista.set_halign(Gtk.Align.START)

        direita.append(titulo_lista)


        info = Gtk.Label(
            label="Duplo clique em uma conexão para conectar."
        )
        info.add_css_class("dim-label")

        info.set_halign(Gtk.Align.START)

        direita.append(info)


        # ====================================================
        # CAMPO DE BUSCA
        # ====================================================

        self.busca_entry = Gtk.SearchEntry()

        self.busca_entry.set_placeholder_text(
            "Pesquisar por nome, IP ou usuário..."
        )

        self.busca_entry.connect(
            "search-changed",
            self.filtrar_lista
        )

        direita.append(self.busca_entry)


        # ====================================================
        # LISTA
        # ====================================================

        self.lista = Gtk.ListBox()

        self.lista.set_selection_mode(
            Gtk.SelectionMode.SINGLE
        )

        self.lista.set_activate_on_single_click(False)

        self.lista.connect(
            "row-activated",
            self.conectar_duplo_clique
        )

        self.lista.set_filter_func(self.funcao_filtro)

        scrolled = Gtk.ScrolledWindow()

        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)

        scrolled.set_child(self.lista)

        direita.append(scrolled)


        # ====================================================
        # BOTÕES
        # ====================================================

        botoes = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10
        )

        direita.append(botoes)


        conectar_button = Gtk.Button(
            label="Conectar"
        )

        conectar_button.add_css_class(
            "suggested-action"
        )

        conectar_button.connect(
            "clicked",
            self.conectar_selecionada
        )

        botoes.append(conectar_button)


        editar_button = Gtk.Button(
            label="Editar"
        )

        editar_button.connect(
            "clicked",
            self.editar_selecionada
        )

        botoes.append(editar_button)


    # ========================================================
    # BACKUP: IMPORTAR / EXPORTAR JSON
    # ========================================================

    def _filtro_json(self):
        filtro = Gtk.FileFilter()
        filtro.set_name("Arquivo JSON (*.json)")
        filtro.add_pattern("*.json")
        filtro.add_mime_type("application/json")

        lista_filtros = Gio.ListStore.new(Gtk.FileFilter)
        lista_filtros.append(filtro)

        return lista_filtros

    def importar_backup(self, button):

        dialog = Gtk.FileDialog()
        dialog.set_title("Selecione o backup (.json) para importar")
        dialog.set_filters(self._filtro_json())

        dialog.open(self, None, self._on_importar_backup_escolhido)

    def _on_importar_backup_escolhido(self, dialog, resultado):

        try:
            arquivo = dialog.open_finish(resultado)
        except GLib.Error:
            # usuário cancelou o diálogo
            return

        if arquivo is None:
            return

        caminho = arquivo.get_path()

        try:
            with open(caminho, "rb") as f:
                blob = f.read()
        except Exception as erro:
            self.mostrar_erro(
                f"Não foi possível ler o arquivo selecionado.\n\n{erro}"
            )
            return

        if blob.startswith(ASSINATURA):
            # Backup criptografado: tenta primeiro com a senha-mestra
            # já usada nessa sessão (caso seja o mesmo cofre/senha).
            self._tentar_descriptografar_backup(blob, self.senha_mestra)
        else:
            # Backup antigo, sem criptografia (compatibilidade).
            try:
                dados = json.loads(blob.decode("utf-8"))
            except Exception as erro:
                self.mostrar_erro(
                    f"Não foi possível ler o arquivo selecionado.\n\n{erro}"
                )
                return
            self._processar_backup_importado(dados)

    def _tentar_descriptografar_backup(self, blob, senha):
        try:
            dados_bytes = descriptografar_bytes(blob, senha)
        except SenhaInvalida:
            self._pedir_senha_backup(blob)
            return
        except Exception as erro:
            self.mostrar_erro(
                f"Não foi possível ler o backup.\n\n{erro}"
            )
            return

        try:
            dados = json.loads(dados_bytes.decode("utf-8"))
        except Exception as erro:
            self.mostrar_erro(
                f"O backup parece corrompido.\n\n{erro}"
            )
            return

        self._processar_backup_importado(dados)

    def _pedir_senha_backup(self, blob):
        # A senha-mestra atual não abriu esse backup — pode ser de
        # outra instalação/senha diferente. Pede a senha específica
        # desse arquivo, sem mexer na senha da sessão atual.

        janela = Gtk.Window(
            transient_for=self,
            modal=True,
            title="Senha do backup",
            resizable=False,
        )

        caixa = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )
        caixa.set_margin_top(24)
        caixa.set_margin_bottom(24)
        caixa.set_margin_start(24)
        caixa.set_margin_end(24)
        janela.set_child(caixa)

        info = Gtk.Label(
            label=(
                "Esse backup está criptografado com uma senha "
                "diferente da atual. Digite a senha usada quando "
                "ele foi exportado."
            )
        )
        info.set_wrap(True)
        info.set_max_width_chars(38)
        caixa.append(info)

        campo = Gtk.PasswordEntry()
        campo.set_show_peek_icon(True)
        campo.set_property("placeholder-text", "Senha do backup")
        caixa.append(campo)

        erro_label = Gtk.Label()
        erro_label.add_css_class("error")
        erro_label.set_visible(False)
        erro_label.set_wrap(True)
        caixa.append(erro_label)

        botao = Gtk.Button(label="Desbloquear backup")
        botao.add_css_class("suggested-action")
        caixa.append(botao)

        def tentar(*_):
            senha = campo.get_text()

            try:
                dados_bytes = descriptografar_bytes(blob, senha)
            except SenhaInvalida:
                erro_label.set_text("Senha incorreta.")
                erro_label.set_visible(True)
                campo.set_text("")
                return
            except Exception as erro:
                erro_label.set_text(f"Erro: {erro}")
                erro_label.set_visible(True)
                return

            janela.destroy()

            try:
                dados = json.loads(dados_bytes.decode("utf-8"))
            except Exception as erro:
                self.mostrar_erro(f"Backup corrompido.\n\n{erro}")
                return

            self._processar_backup_importado(dados)

        botao.connect("clicked", tentar)
        campo.connect("activate", tentar)

        janela.present()
        campo.grab_focus()

    def _processar_backup_importado(self, dados):

        if not isinstance(dados, list):
            self.mostrar_erro(
                "O arquivo não parece ser um backup válido do "
                "RDP Manager (esperava uma lista de conexões)."
            )
            return

        validas = [item for item in dados if validar_conexao(item)]
        ignoradas = len(dados) - len(validas)

        if not validas:
            self.mostrar_erro(
                "Nenhuma conexão válida foi encontrada nesse arquivo."
            )
            return

        # Mescla com o que já existe: entradas com o mesmo "name"
        # são substituídas pela versão do backup; o resto é mantido.
        nomes_existentes = {c["name"]: i for i, c in enumerate(self.conexoes)}

        novas = 0
        atualizadas = 0

        for item in validas:

            registro = {
                "name": item["name"],
                "host": item["host"],
                "username": item["username"],
                "password": item.get("password", ""),
                "created_at": item.get(
                    "created_at",
                    datetime.now().isoformat(timespec="seconds")
                ),
                "last_used": item.get("last_used", ""),
            }

            if registro["name"] in nomes_existentes:
                self.conexoes[nomes_existentes[registro["name"]]] = registro
                atualizadas += 1
            else:
                self.conexoes.append(registro)
                nomes_existentes[registro["name"]] = len(self.conexoes) - 1
                novas += 1

        salvar_conexoes(self.conexoes, self.senha_mestra)
        self.atualizar_lista()

        resumo = (
            f"Importação concluída.\n\n"
            f"Novas conexões: {novas}\n"
            f"Atualizadas: {atualizadas}"
        )

        if ignoradas:
            resumo += f"\nIgnoradas (sem nome/host/usuário): {ignoradas}"

        self.mostrar_info(resumo)

    def exportar_backup(self, button):

        dialog = Gtk.FileDialog()
        dialog.set_title("Salvar backup como...")
        dialog.set_filters(self._filtro_json())

        nome_sugerido = (
            f"rdp-manager-backup-"
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        dialog.set_initial_name(nome_sugerido)

        dialog.save(self, None, self._on_exportar_backup_escolhido)

    def _on_exportar_backup_escolhido(self, dialog, resultado):

        try:
            arquivo = dialog.save_finish(resultado)
        except GLib.Error:
            # usuário cancelou o diálogo
            return

        if arquivo is None:
            return

        caminho = arquivo.get_path()

        try:
            dados_bytes = json.dumps(
                self.conexoes,
                indent=2,
                ensure_ascii=False
            ).encode("utf-8")

            blob = criptografar_bytes(dados_bytes, self.senha_mestra)

            with open(caminho, "wb") as f:
                f.write(blob)
        except Exception as erro:
            self.mostrar_erro(
                f"Não foi possível salvar o backup.\n\n{erro}"
            )
            return

        self.mostrar_info(f"Backup salvo em:\n{caminho}")


    # ========================================================
    # LABEL
    # ========================================================

    def criar_label(self, texto):

        label = Gtk.Label(label=texto)

        label.set_halign(Gtk.Align.START)

        return label


    def atualizar_lista(self):

        # Remover todas as linhas atuais
        while True:

            row = self.lista.get_row_at_index(0)

            if row is None:
                break

            self.lista.remove(row)


        # Ordenar pelas conexões mais recentemente utilizadas
        self.conexoes.sort(
            key=lambda x: x.get("last_used", ""),
            reverse=True
        )


        # Conectadas primeiro (sort estável preserva a ordem por
        # "último uso" já aplicada acima dentro de cada grupo)
        self.conexoes.sort(
            key=lambda x: x["name"] not in self.processos_ativos
        )


        # Descarta referências de labels de ping da renderização
        # anterior (widgets antigos serão destruídos ao reconstruir
        # a lista).
        self.labels_ping = {}

        # Criar as linhas
        for conexao in self.conexoes:

            conectado = conexao["name"] in self.processos_ativos

            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=3
            )

            box.add_css_class("card")
            box.add_css_class("rdp-row")

            if conectado:
                box.add_css_class("rdp-row-ativa")

            box.set_margin_top(12)
            box.set_margin_bottom(12)
            box.set_margin_start(15)
            box.set_margin_end(15)


            # Linha do nome + indicador de status
            linha_nome = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=6
            )

            icone = Gtk.Image.new_from_icon_name("computer-symbolic")
            icone.set_pixel_size(16)
            linha_nome.append(icone)

            if conectado:
                ponto = Gtk.Label(label="●")
                ponto.add_css_class("rdp-ponto-ativo")
                linha_nome.append(ponto)

            nome = Gtk.Label()

            nome.set_markup(
                f"<b>{GLib.markup_escape_text(conexao['name'])}</b>"
            )
            nome.add_css_class("rdp-nome")

            nome.set_halign(Gtk.Align.START)

            linha_nome.append(nome)

            if conectado:
                ping_ms = self.pings.get(conexao["name"])

                if ping_ms is not None:
                    texto_selo = f"Conectado · {ping_ms}ms"
                else:
                    texto_selo = "Conectado · medindo…"

                selo = Gtk.Label(label=texto_selo)
                selo.add_css_class("rdp-selo-ativo")
                selo.add_css_class("caption")
                linha_nome.append(selo)

                self.labels_ping[conexao["name"]] = selo

            box.append(linha_nome)


            # IP e usuário
            detalhes = Gtk.Label(
                label=(
                    f"{conexao['host']}    •    "
                    f"{conexao['username']}"
                )
            )
            detalhes.add_css_class("dim-label")

            detalhes.set_halign(Gtk.Align.START)

            box.append(detalhes)


            # Criar linha
            row = Gtk.ListBoxRow()

            row.set_child(box)

            # Guardar conexão na linha
            row.conexao = conexao

            self.lista.append(row)

    # ========================================================
    # BUSCA / FILTRO
    # ========================================================

    def filtrar_lista(self, entry):

        self.texto_filtro = entry.get_text().strip().lower()

        self.lista.invalidate_filter()


    def funcao_filtro(self, row):

        if not self.texto_filtro:
            return True

        conexao = row.conexao

        campos = (
            conexao.get("name", ""),
            conexao.get("host", ""),
            conexao.get("username", "")
        )

        return any(
            self.texto_filtro in campo.lower()
            for campo in campos
        )


    # ========================================================
    # ATUALIZAR LISTA
    # ========================================================
    def salvar_conexao(self, button):

        nome = self.nome_entry.get_text().strip()
        host = self.host_entry.get_text().strip()
        usuario = self.usuario_entry.get_text().strip()
        senha = self.senha_entry.get_text()

        if not nome or not host or not usuario:
            self.mostrar_erro(
                "Nome, IP/Host e usuário são obrigatórios."
            )
            return

        agora = datetime.now().isoformat(
            timespec="seconds"
        )

        conexao_para_abrir = None

        # Editando e renomeou: remove a versão com o nome antigo
        if self.editando_nome and self.editando_nome != nome:
            self.conexoes = [
                c for c in self.conexoes
                if c["name"] != self.editando_nome
            ]

        # Procurar conexão existente
        for conexao in self.conexoes:

            if conexao["name"] == nome:

                conexao["host"] = host
                conexao["username"] = usuario
                conexao["password"] = senha
                conexao["last_used"] = agora

                conexao_para_abrir = conexao
                break

        # Se não existir, criar nova conexão
        if conexao_para_abrir is None:

            conexao_para_abrir = {
                "name": nome,
                "host": host,
                "username": usuario,
                "password": senha,
                "created_at": agora,
                "last_used": agora
            }

            self.conexoes.append(conexao_para_abrir)

        # Salvar no JSON
        salvar_conexoes(self.conexoes, self.senha_mestra)

        # Atualizar lista
        self.atualizar_lista()

        # Fechar formulário (também limpa os campos)
        self.janela_form.close()

        # Conectar automaticamente
        self.conectar(conexao_para_abrir)

    # ========================================================
    # LIMPAR
    # ========================================================

    def limpar_formulario(self, *args):

        self.nome_entry.set_text("")
        self.host_entry.set_text("")
        self.usuario_entry.set_text("")
        self.senha_entry.set_text("")

        self.editando_nome = None

        self.salvar_button.set_label(
            "Salvar conexão"
        )

        self.excluir_button.set_visible(False)

    def abrir_formulario_nova(self, *args):
        self.limpar_formulario()
        self.janela_form.set_title("Nova conexão")
        self.janela_form.present()
        self.nome_entry.grab_focus()


    # ========================================================
    # SELECIONAR
    # ========================================================

    def obter_selecionada(self):

        row = self.lista.get_selected_row()

        if row is None:
            return None

        return row.conexao


    # ========================================================
    # CONECTAR
    # ========================================================

    def conectar_selecionada(self, button):

        conexao = self.obter_selecionada()

        if conexao is None:

            self.mostrar_erro(
                "Selecione uma conexão primeiro."
            )

            return

        self.conectar(conexao)


    # ========================================================
    # DUPLO CLIQUE
    # ========================================================

    def conectar_duplo_clique(self, lista, row):

        conexao = row.conexao

        self.conectar(conexao)


    # ========================================================
    # PING / LATÊNCIA DAS CONEXÕES ATIVAS
    # ========================================================

    def _tick_pings(self):

        for nome in list(self.processos_ativos.keys()):

            conexao = next(
                (c for c in self.conexoes if c["name"] == nome),
                None
            )

            if conexao is None:
                continue

            threading.Thread(
                target=self._medir_e_atualizar_ping,
                args=(nome, conexao["host"]),
                daemon=True
            ).start()

        return True  # continua repetindo a cada 4 segundos

    def _medir_e_atualizar_ping(self, nome, host):
        ms = medir_latencia_tcp(host)
        GLib.idle_add(self._aplicar_ping, nome, ms)

    def _aplicar_ping(self, nome, ms):

        # Só atualiza se ainda estiver conectada (evita mostrar um
        # ping "fantasma" de uma conexão que já foi fechada nesse
        # meio tempo).
        if nome in self.processos_ativos:
            self.pings[nome] = ms
            self.atualizar_lista()

        return False  # não repetir (é um idle_add de disparo único)


    # ========================================================
    # FOCAR JANELA JÁ CONECTADA
    # ========================================================

    def _titulo_janela_rdp(self, nome_conexao):
        return gerar_titulo_janela_rdp(nome_conexao)

    def focar_janela_existente(self, nome_conexao):

        titulo = self._titulo_janela_rdp(nome_conexao)

        if focar_janela_por_titulo(titulo):
            return

        self.mostrar_info(
            "Essa conexão já está aberta, mas não consegui trazer a "
            "janela pra frente automaticamente.\n\n"
            "Instale o 'wmctrl' (sudo dnf install wmctrl / sudo apt "
            "install wmctrl) pra essa função funcionar, ou procure a "
            f"janela manualmente: \"{titulo}\"."
        )


    # ========================================================
    # EXECUTAR FREERDP
    # ========================================================

    def conectar(self, conexao):

        # Já existe uma sessão aberta pra essa conexão? Em vez de
        # abrir outra, só traz a janela existente pra frente.
        processo_existente = self.processos_ativos.get(conexao["name"])

        if processo_existente is not None and processo_existente.poll() is None:
            self.focar_janela_existente(conexao["name"])
            return

        if self.conectando:
            # já existe uma conexão sendo aberta, ignora o clique
            return

        self.conectando = True
        self.definir_interface_ocupada(True)

        agora = datetime.now().isoformat(
            timespec="seconds"
        )

        conexao["last_used"] = agora

        titulo_janela = self._titulo_janela_rdp(conexao["name"])

        # Prefere o FreeRDP instalado no sistema (bem mais rápido);
        # usa o embutido no AppImage só se não houver nenhum.
        executavel, env_freerdp, origem_freerdp = resolver_freerdp()
        print(f"[rdp-manager] FreeRDP ({origem_freerdp}): {executavel}", flush=True)

        comando = [
            executavel,
            f"/v:{conexao['host']}",
            f"/u:{conexao['username']}",
            f"/p:{conexao.get('password', '')}",
            "/cert:ignore",
            "/dynamic-resolution",
            "/clipboard",
            "/bpp:32",
            "/gfx",  # codec gráfico moderno (Win10/11): com /bpp:16 a tela pode congelar
            "/log-level:ERROR",  # menos saída = menos overhead
            "/kbd:layout:0x00010416",  # ABNT2 (PT-BR) — evita o
                                        # autodetect errado de layout
                                        # que troca Ctrl/A por outras teclas
            f"/t:{titulo_janela}",  # título fixo, usado depois pra
                                     # localizar e focar essa janela
            "-themes",
            "-wallpaper",
            "-window-drag",
            "-menu-anims",
            "-aero"
        ]

        try:

            # Saída vai pra um arquivo temporário: com PIPE, se
            # ninguém lê, o buffer enche e o xfreerdp trava/fica lento.
            log_saida = tempfile.TemporaryFile(mode="w+")
            processo = subprocess.Popen(
                comando,
                stdout=log_saida,
                stderr=subprocess.STDOUT,
                text=True,
                env=env_freerdp
            )
            processo.log_saida = log_saida

            # Salvar (PBKDF2, lento) fora da thread da interface e
            # depois de já ter aberto o FreeRDP.
            threading.Thread(
                target=salvar_conexoes,
                args=(list(self.conexoes), self.senha_mestra),
                daemon=True
            ).start()

            # Marca como conectada imediatamente (o processo já está
            # de pé) e atualiza a lista pra mostrar o ícone verde e
            # subir essa conexão pro topo.
            self.processos_ativos[conexao["name"]] = processo
            self.atualizar_lista()

            GLib.timeout_add(
                500,
                self.verificar_processo_rdp,
                processo,
                conexao
            )

            # Libera novos cliques automaticamente após alguns
            # segundos, tempo suficiente pro xfreerdp abrir a janela
            GLib.timeout_add_seconds(
                2,
                self.liberar_interface
            )
        except FileNotFoundError:

            self.mostrar_erro(
                "FreeRDP não encontrado.\n\n"
                "Verifique se o comando 'xfreerdp' está instalado "
                "e disponível no PATH."
            )
            self.liberar_interface()

        except Exception as erro:

            self.mostrar_erro(
                f"Erro ao executar o FreeRDP:\n\n{erro}"
            )
            self.liberar_interface()


    def liberar_interface(self):
        self.conectando = False
        self.definir_interface_ocupada(False)
        return False  # necessário para o GLib.timeout_add_seconds não repetir


    def definir_interface_ocupada(self, ocupada):
        # Desabilita a lista e os botões enquanto uma conexão abre,
        # evitando duplo clique / cliques repetidos no "Conectar"
        self.lista.set_sensitive(not ocupada)
        self.salvar_button.set_sensitive(not ocupada)


    def verificar_processo_rdp(self, processo, conexao):

        # Enquanto o FreeRDP estiver executando, não fazemos nada.
        if processo.poll() is None:
            return True

        # O processo terminou; agora podemos ler a saída sem
        # bloquear a interface.
        try:
            processo.log_saida.seek(0)
            saida = processo.log_saida.read()[-4000:]
            processo.log_saida.close()
        except Exception:
            saida = ""

        codigo = processo.returncode

        # Não está mais conectada: tira o "verde" e a ordenação de topo
        if self.processos_ativos.get(conexao["name"]) is processo:
            del self.processos_ativos[conexao["name"]]
            self.pings.pop(conexao["name"], None)

        self.atualizar_lista()

        # Encerramento normal.
        if codigo == 0:
            return False

        erro = saida.strip() or f"Código de erro: {codigo}"

        self.mostrar_erro(
            f"A conexão RDP foi encerrada.\n\n"
            f"Servidor: {conexao['host']}\n"
            f"Usuário: {conexao['username']}\n\n"
            f"Detalhes:\n{erro}"
        )

        return False


    # ========================================================
    # EDITAR
    # ========================================================

    def editar_selecionada(self, button):

        conexao = self.obter_selecionada()

        if conexao is None:

            self.mostrar_erro(
                "Selecione uma conexão primeiro."
            )

            return


        self.nome_entry.set_text(
            conexao["name"]
        )

        self.host_entry.set_text(
            conexao["host"]
        )

        self.usuario_entry.set_text(
            conexao["username"]
        )

        self.senha_entry.set_text(
            conexao.get("password", "")
        )


        self.editando_nome = conexao["name"]

        self.salvar_button.set_label(
            "Salvar alterações"
        )

        self.excluir_button.set_visible(True)

        self.janela_form.set_title("Editar conexão")
        self.janela_form.present()


    # ========================================================
    # EXCLUIR
    # ========================================================

    def excluir_selecionada(self, button):

        conexao = next(
            (c for c in self.conexoes if c["name"] == self.editando_nome),
            None
        )

        if conexao is None:
            return


        dialog = Gtk.AlertDialog()

        dialog.set_message(
            "Excluir conexão?"
        )

        dialog.set_detail(
            f"Você deseja excluir '{conexao['name']}'?"
        )

        dialog.set_buttons([
            "Cancelar",
            "Excluir"
        ])

        dialog.set_cancel_button(0)
        dialog.set_default_button(1)


        dialog.choose(
            self.janela_form,
            None,
            self.confirmar_exclusao,
            conexao
        )


    def confirmar_exclusao(
        self,
        dialog,
        resultado,
        conexao
    ):

        try:

            resposta = dialog.choose_finish(
                resultado
            )

            if resposta != 1:
                return

        except Exception:
            return


        self.conexoes = [
            c for c in self.conexoes
            if c["name"] != conexao["name"]
        ]

        salvar_conexoes(self.conexoes, self.senha_mestra)

        self.atualizar_lista()

        self.janela_form.close()


    # ========================================================
    # MENSAGENS
    # ========================================================

    def mostrar_erro(self, mensagem):
        self.mostrar_dialogo_mensagem("Erro", mensagem)


    def mostrar_info(self, mensagem):
        self.mostrar_dialogo_mensagem("RDP Manager", mensagem)


    def mostrar_dialogo_mensagem(self, titulo, mensagem):

        # Janela pequena, modal e sempre fechável (em vez do
        # Gtk.AlertDialog nativo, que às vezes abre grande demais)
        janela = Gtk.Window()

        janela.set_title(titulo)
        janela.set_transient_for(self)
        janela.set_modal(True)
        janela.set_default_size(380, 200)
        janela.set_resizable(True)

        caixa = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )

        caixa.set_margin_top(15)
        caixa.set_margin_bottom(15)
        caixa.set_margin_start(15)
        caixa.set_margin_end(15)

        janela.set_child(caixa)


        titulo_label = Gtk.Label()
        titulo_label.set_markup(
            f"<b>{GLib.markup_escape_text(titulo)}</b>"
        )
        titulo_label.set_halign(Gtk.Align.START)

        caixa.append(titulo_label)


        # Área rolável para o texto, para a mensagem não
        # estourar o tamanho da janela quando for longa
        rolagem = Gtk.ScrolledWindow()
        rolagem.set_vexpand(True)
        rolagem.set_hexpand(True)
        rolagem.set_policy(
            Gtk.PolicyType.AUTOMATIC,
            Gtk.PolicyType.AUTOMATIC
        )

        texto_label = Gtk.Label(label=mensagem)
        texto_label.set_wrap(True)
        texto_label.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        texto_label.set_halign(Gtk.Align.START)
        texto_label.set_valign(Gtk.Align.START)
        texto_label.set_selectable(True)
        texto_label.set_xalign(0)

        rolagem.set_child(texto_label)

        caixa.append(rolagem)


        ok_button = Gtk.Button(label="OK")
        ok_button.add_css_class("suggested-action")
        ok_button.set_halign(Gtk.Align.END)

        ok_button.connect(
            "clicked",
            lambda botao: janela.close()
        )

        caixa.append(ok_button)

        janela.present()

