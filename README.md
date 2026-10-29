# RDP Manager — pacote AppImage (com FreeRDP embutido)

Diferente do Flatpak, o AppImage **não usa sandbox**. O app roda como
um processo comum do seu usuário — por isso o comportamento de
copiar/colar arquivos pela sessão RDP fica igual ao de um programa
instalado direto na distro (`xfreerdp` do jeito que o script sempre
usou), sem precisar liberar permissão de filesystem nenhuma.

## Estrutura

```
rdp-manager-appimage/
├── build.sh                          # script que gera o .AppImage final
└── AppDir/
    ├── AppRun                        # ponto de entrada do app
    ├── br.com.rdpmanager.desktop     # atalho
    ├── br.com.rdpmanager.svg         # ícone
    └── usr/
        ├── bin/                      # xfreerdp vai ser copiado pra cá pelo build.sh
        └── share/
            ├── rdp-manager/rdp-manager.py   # seu script (BASE_DIR já ajustado)
            ├── applications/
            └── icons/...
```

## Por que preciso rodar o build.sh na SUA máquina?

Empacotar em AppImage exige compilar o FreeRDP e "aspirar" as
bibliotecas do GTK4 do sistema onde você compila. Isso precisa
acontecer numa máquina Linux de verdade, com GTK4, FUSE, compilador
etc. instalados — coisas que este ambiente de chat não tem. O
`build.sh` automatiza tudo isso: instala as dependências de build via
`apt`, compila o FreeRDP, baixa as ferramentas de empacotamento
(`linuxdeploy` + plugin GTK) e gera o `.AppImage` final.

## Nota específica para Fedora

O `build.sh` já detecta automaticamente se você está no Fedora (usa
`dnf`) ou Ubuntu/Debian (usa `apt`) e instala os pacotes certos para
cada um.

Duas coisas para ficar de olho no Fedora:

1. **FUSE**: o AppImage tradicionalmente depende do `libfuse2`
   (FUSE versão 2), não do FUSE3 que já vem por padrão em Fedoras mais
   recentes. Se ao tentar *rodar* o `.AppImage` você ver um erro tipo
   `dlopen(): error loading libfuse.so.2` ou `AppImages require FUSE
   to run`, instale a compatibilidade:
   ```bash
   sudo dnf install fuse fuse-libs
   ```
   Se mesmo assim não funcionar, existe uma alternativa sem FUSE: rodar
   com `--appimage-extract-and-run` em vez de executar direto (isso
   extrai o conteúdo pra uma pasta temporária e roda de lá, sem
   precisar montar via FUSE):
   ```bash
   ./RDP_Manager-x86_64.AppImage --appimage-extract-and-run
   ```

2. **glibc mais nova**: compilar no Fedora 44 gera um binário que
   depende da versão da glibc dele, que é mais recente que a de
   distros mais antigas. Isso não é problema nenhum se você vai usar
   o AppImage só na sua própria máquina ou em distros de versão igual
   ou mais nova. Só evite gerar o pacote no Fedora se o plano for
   rodá-lo depois num Ubuntu 20.04/22.04 antigo, por exemplo — nesse
   caso o ideal seria compilar numa distro mais antiga.

## Recomendação de máquina para compilar

Use a distro **mais antiga possível** que você tiver disponível (ex.:
Ubuntu 22.04), porque AppImage segue a regra "compile no mais velho,
rode no mais novo": um binário compilado no Ubuntu 22.04 roda sem
problema no Ubuntu 24.04, Fedora recente, etc., mas o inverso pode
falhar por incompatibilidade de versão da glibc. Se você só tem uma
distro recente à mão, ainda funciona, só que pode não rodar em
distros mais antigas que a sua.

## Como gerar o .AppImage

```bash
cd rdp-manager-appimage
chmod +x build.sh
./build.sh
```

Isso vai:
1. Instalar dependências de build (`sudo apt install ...`)
2. Baixar e compilar o FreeRDP 3.5.1 (cliente `xfreerdp` estático)
3. Copiar o `xfreerdp` e suas bibliotecas pra dentro do `AppDir`
4. Baixar `linuxdeploy` + plugin GTK
5. Empacotar tudo (GTK4, Python, PyGObject, FreeRDP) num único
   arquivo: `RDP_Manager-x86_64.AppImage`

O processo leva alguns minutos (a compilação do FreeRDP é a parte
mais demorada).

## Rodar / distribuir

```bash
chmod +x RDP_Manager-x86_64.AppImage
./RDP_Manager-x86_64.AppImage
```

Esse único arquivo já é o que você distribui pra qualquer outra
máquina Linux — não precisa instalar nada lá, só dar permissão de
execução e rodar. Nenhum `apt install` de dependência é necessário no
destino, já que tudo (GTK4, Python, FreeRDP) está embutido.

## O que funciona diferente do Flatpak

- ✅ Copiar arquivo de **qualquer pasta** e colar dentro da sessão RDP: funciona direto, sem configurar nada, porque não há sandbox.
- ✅ Nenhuma dependência external a instalar no computador de destino.
- ⚠️ Sem o isolamento de segurança do Flatpak: o app roda com os mesmos privilégios do seu usuário, como qualquer programa "normal" instalado via `.deb`/`apt`. Isso é o preço de não ter sandbox — não é um problema exclusivo deste app, é assim que praticamente todo software de desktop tradicional funciona.
- ⚠️ Não atualiza sozinho. Se quiser atualização automática, dá pra integrar depois com `AppImageUpdate`, mas isso é um passo extra (exige hospedar as releases em algum lugar, tipo GitHub Releases).

## Lembrete sobre a senha em texto puro

Assim como no Flatpak, o `connections.json` continua guardando a
senha em texto plano (só protegido por permissão de arquivo `0600`).
Isso é do código original, independe do empacotamento. Se quiser, dá
pra migrar isso pra um cofre de senhas do sistema (`libsecret`) depois.

## Qual FreeRDP o app usa?

Ao conectar, o app procura `xfreerdp3` / `xfreerdp` já instalado no
sistema e, se achar, usa **ele** (com as bibliotecas do sistema, não as
do AppImage) — desempenho igual ao de rodar o FreeRDP por fora. Se não
houver nenhum instalado, usa o `xfreerdp` embutido. Para forçar o
embutido: `RDPM_FREERDP=embutido ./RDP_Manager-x86_64.AppImage`.
O terminal mostra a linha `[rdp-manager] FreeRDP (sistema|embutido): caminho`.

## Aviso de instalação/atualização do FreeRDP

Ao abrir o app (e pelo botão de atualização na barra de título), ele
verifica em segundo plano o FreeRDP da máquina:

- **Não instalado** → janela oferecendo "Instalar o FreeRDP mais recente".
- **Versão mais nova nos repositórios da distro** → janela "Atualizar".

O botão faz tudo sozinho: o sistema pede a senha de administrador
(`pkexec`), o app instala/atualiza via `apt`, `dnf`, `zypper` ou
`pacman` e avisa quando termina — sem reiniciar. As escolhas "Não
perguntar novamente" / "Ignorar esta versão" ficam em
`~/.local/share/rdp-manager/config.json`.
