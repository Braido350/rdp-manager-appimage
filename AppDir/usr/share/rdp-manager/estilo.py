#!/usr/bin/env python3
"""
CSS e aplicação de tema do RDP Manager. Usa classes nativas do
GTK4/Adwaita (card, dim-label, caption) quando possível, em vez de
cores fixas, pra respeitar automaticamente o tema claro/escuro do
sistema. As cores fixas que existem aqui (verde de status "ativo")
são propositais e seguras em qualquer tema, por serem usadas como
destaque (borda/texto), não como fundo de página.
"""

from gi.repository import Gtk, Gdk


CSS_MODERNO = """
.rdp-titulo {
    font-size: 21px;
    font-weight: 800;
    letter-spacing: -0.3px;
}

entry {
    border-radius: 10px;
    padding: 8px 10px;
}

button {
    border-radius: 10px;
}

headerbar {
    box-shadow: none;
}

.rdp-row {
    margin: 5px 10px;
    padding: 2px;
}

.rdp-row-ativa {
    border: 2px solid #26a269;
    border-radius: 12px;
}

.rdp-ponto-ativo {
    color: #26a269;
    font-size: 16px;
    font-weight: 900;
}

.rdp-selo-ativo {
    color: #26a269;
    font-weight: 700;
}

.rdp-nome {
    font-size: 14px;
}

.suggested-action {
    font-weight: 600;
}
"""


def aplicar_css_moderno():
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS_MODERNO)

    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
