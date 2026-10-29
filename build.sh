#!/bin/bash
set -e
#
# Build do RDP Manager em AppImage — com FreeRDP embutido.
#
# Rode este script numa distro Ubuntu/Debian (recomendado: uma versão
# um pouco mais antiga, tipo Ubuntu 22.04, para máxima compatibilidade
# do AppImage com glibc de outras distros — "compile no mais velho,
# rode no mais novo" é a regra de ouro do AppImage).
#
# Uso:
#   chmod +x build.sh
#   ./build.sh
#
# Resultado: RDP_Manager-x86_64.AppImage na pasta atual.

APPDIR="$(pwd)/AppDir"
BUILD_DIR="$(pwd)/build-tmp"
FREERDP_VERSION="3.26.0"

echo "==> 1/5 Instalando dependências de sistema para compilar"
if command -v dnf >/dev/null 2>&1; then
    # Fedora — habilita o RPM Fusion se ainda não estiver, necessário
    # para o ffmpeg-devel "completo" (o do repositório oficial do
    # Fedora não tem suporte a H.264 por questão de licenciamento).
    if ! rpm -q rpmfusion-free-release >/dev/null 2>&1; then
        sudo dnf install -y \
          "https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm" \
          "https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm"
    fi

    sudo dnf install -y \
        gcc gcc-c++ cmake ninja-build pkgconf-pkg-config git wget \
        gtk4-devel gobject-introspection-devel \
        python3 python3-pip python3-gobject python3-cairo \
        openssl-devel zlib-devel \
        libX11-devel libXext-devel libXrandr-devel libXi-devel \
        libXrender-devel libXfixes-devel libXcursor-devel \
        wayland-devel wayland-protocols-devel libxkbcommon-devel \
        pulseaudio-libs-devel fuse fuse-libs fuse3-devel \
        ffmpeg ffmpeg-devel openh264-devel libva-devel \
        python3-cryptography wmctrl
elif command -v apt >/dev/null 2>&1; then
    # Ubuntu/Debian
    sudo apt update
    sudo apt install -y \
        build-essential cmake ninja-build pkg-config git wget \
        libgtk-4-dev gobject-introspection libgirepository1.0-dev \
        python3 python3-pip python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
        libssl-dev zlib1g-dev libx11-dev libxext-dev libxrandr-dev \
        libxi-dev libxrender-dev libxfixes-dev libxcursor-dev \
        libwayland-dev wayland-protocols libxkbcommon-dev libpulse-dev fuse \
        libavcodec-dev libavutil-dev libswscale-dev libopenh264-dev libva-dev \
        python3-cryptography wmctrl
else
    echo "Distro não reconhecida (nem dnf nem apt encontrados)."
    echo "Instale manualmente os equivalentes de: gtk4-devel, gobject-introspection-devel,"
    echo "python3-gobject, cmake, ninja, openssl-devel, libX11-devel, ffmpeg-devel,"
    echo "openh264-devel, libva-devel e afins, e rode de novo."
    exit 1
fi

echo "==> 2/5 Compilando o FreeRDP (estático, só o cliente xfreerdp)"
mkdir -p "$BUILD_DIR" && cd "$BUILD_DIR"
if [ ! -d FreeRDP ]; then
    wget -O freerdp.tar.gz \
      "https://github.com/FreeRDP/FreeRDP/releases/download/${FREERDP_VERSION}/freerdp-${FREERDP_VERSION}.tar.gz"
    mkdir FreeRDP && tar xf freerdp.tar.gz -C FreeRDP --strip-components=1
fi
cd FreeRDP
# Se aparecer erro de compilação em dsp_ffmpeg.c / h264_ffmpeg.c
# (incompatibilidade entre FreeRDP e uma versão muito nova do FFmpeg
# do seu sistema), troque WITH_FFMPEG e WITH_SWSCALE pra OFF logo
# abaixo — o app funciona normalmente sem isso, só perde o decoder
# H.264 alternativo via FFmpeg e áudio AAC no redirecionamento de
# microfone (o OpenH264 já cobre o H.264 sozinho).
cmake -B build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DWITH_SERVER=OFF \
    -DWITH_SHADOW=OFF \
    -DWITH_CLIENT=ON \
    -DWITH_X11=ON \
    -DWITH_WAYLAND=ON \
    -DWITH_PULSE=ON \
    -DWITH_CUPS=OFF \
    -DWITH_KRB5=OFF \
    -DWITH_PCSC=OFF \
    -DWITH_PKCS11=OFF \
    -DWITH_FFMPEG=ON \
    -DWITH_SWSCALE=ON \
    -DWITH_CAIRO=OFF \
    -DWITH_OPENH264=ON \
    -DWITH_VAAPI=ON \
    -DWITH_JPEG=OFF \
    -DCHANNEL_URBDRC=OFF \
    -DBUILD_TESTING=OFF
cmake --build build --parallel "$(nproc)"

echo "==> 3/5 Copiando o xfreerdp e libs para dentro do AppDir"
cp build/client/X11/xfreerdp "$APPDIR/usr/bin/"
mkdir -p "$APPDIR/usr/lib"
# Copia as .so do FreeRDP que ele mesmo gerou (winpr, freerdp, etc.)
find build -name "*.so*" -exec cp -P {} "$APPDIR/usr/lib/" \;

echo "==> 4/5 Baixando ferramentas de empacotamento (linuxdeploy)"
cd "$BUILD_DIR"
[ -f linuxdeploy-x86_64.AppImage ] || wget \
  "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
[ -f linuxdeploy-plugin-gtk.sh ] || wget \
  "https://raw.githubusercontent.com/linuxdeploy/linuxdeploy-plugin-gtk/master/linuxdeploy-plugin-gtk.sh"
chmod +x linuxdeploy-x86_64.AppImage linuxdeploy-plugin-gtk.sh

echo "==> 5/5 Gerando o .AppImage final (empacota GTK4 + Python + libs)"
cd "$(dirname "$APPDIR")"
export DEPLOY_GTK_VERSION=4
export PATH="$BUILD_DIR:$PATH"
"$BUILD_DIR/linuxdeploy-x86_64.AppImage" \
    --appdir "$APPDIR" \
    --plugin gtk \
    --desktop-file "$APPDIR/br.com.rdpmanager.desktop" \
    --icon-file "$APPDIR/br.com.rdpmanager.svg" \
    --output appimage

mv RDP_Manager*.AppImage RDP_Manager-x86_64.AppImage 2>/dev/null || true
echo ""
echo "Pronto: RDP_Manager-x86_64.AppImage"
echo "Teste com: chmod +x RDP_Manager-x86_64.AppImage && ./RDP_Manager-x86_64.AppImage"
