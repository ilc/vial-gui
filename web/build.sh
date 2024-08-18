#!/bin/bash

set -e

source /vial-web/version.sh
source /vial-web/emsdk/emsdk_env.sh

mkdir -p build
rm -rf build/*

pushd build

VIAL_VER=$(git rev-parse HEAD)
WEB_VER=$(git rev-parse HEAD)
VIA_STACK_VER="UNKNOWN"
UNIQVER=$(echo ${VIAL_VER} ${WEB_VER} ${VIA_STACK_VER} | sha256sum | awk '{print $1}')

cp ../icon.png .
cp -r /vial-web/deps/cpython/builddir/emscripten-browser/usr .
cp /vial-web/via-keymap-precompiled/via_keyboard_stack.json usr/local/via_keyboards.json
cp ../../src/main/resources/base/qmk_settings.json usr/local
cp ../../src/build/settings/base.json usr/local/build_settings.json
cp -r ../../src/main/python/* usr/local/lib/python3.11
cp ../simpleeval.py usr/local/lib/python3.11
emcc \
    --preload-file="./usr/local" \
    -I /vial-web/deps/cpython/Include/ \
    -I /vial-web/deps/cpython/builddir/emscripten-browser/ \
    -I /vial-web/deps/cpython/Include/internal/ \
    /vial-web/deps/cpython/builddir/emscripten-browser/libpython3.11.a \
    /vial-web/deps/cpython/builddir/emscripten-browser/Modules/_decimal/libmpdec/libmpdec.a \
    /vial-web/deps/cpython/builddir/emscripten-browser/Modules/expat/libexpat.a  \
    -sALLOW_MEMORY_GROWTH \
    -sTOTAL_MEMORY=20971520 \
    -sFORCE_FILESYSTEM \
    -sTEXTDECODER=0 \
    -lidbfs.js \
    -lnodefs.js \
    -lproxyfs.js \
    -lworkerfs.js \
    -O2 -g0 \
    -o main-${UNIQVER}.js \
    -ldl \
    -lm \
    -sUSE_ZLIB \
    -sUSE_BZIP2 \
    -sUSE_ZLIB \
    -L /vial-web/deps/PyQt5-${PYQT5_VER}/QtCore \
    -L /vial-web/deps/qt5/qtbase/lib \
    -L /vial-web/deps/PyQt5_sip-${PYQT5SIP_VER} \
    -L /vial-web/deps/PyQt5-${PYQT5_VER}/QtGui \
    -L /vial-web/deps/PyQt5-${PYQT5_VER}/QtWidgets \
    -L /vial-web/deps/qt5/qtbase/plugins/platforms \
    -L /vial-web/deps/PyQt5-${PYQT5_VER}/QtSvg \
    -L /vial-web/deps/qt5/qtbase/plugins/iconengines \
    -L /vial-web/deps/qt5/qtbase/plugins/imageformats \
    -l QtCore \
    -l Qt5Core \
    -l sip \
    -l QtGui \
    -l QtWidgets \
    -l Qt5Core \
    -l Qt5Gui \
    -l Qt5Widgets \
    -l qwasm \
    -l Qt5FontDatabaseSupport \
    -l qminimal \
    -l Qt5EventDispatcherSupport \
    -l qoffscreen \
    --bind \
    -l qtharfbuzz \
    -l QtSvg \
    -l qsvgicon \
    -l qjpeg \
    -l qsvg \
    -l Qt5Svg \
    -s USE_FREETYPE=1 \
    -s USE_LIBPNG=1 \
    -lqtpcre2 \
    -pthread \
    -sDISABLE_DEPRECATED_FIND_EVENT_TARGET_BEHAVIOR=0 \
    -s EXTRA_EXPORTED_RUNTIME_METHODS=\["UTF16ToString","stringToUTF16","getValue","setValue"\] \
    -sEXPORTED_FUNCTIONS=\["_PyRun_SimpleString","_vialglue_set_response","_vialglue_set_response_error","_vialglue_set_device_desc","_main"\] \
    -sPROXY_TO_PTHREAD \
    -sOFFSCREENCANVAS_SUPPORT \
    -L /vial-web/deps/xz-${XZ_VER}/prefix/lib/ \
    -llzma \
    ../main.c
cp ../index.html .
cat ../worker.js >> main-${UNIQVER}.worker.js
sed -i 's+err("worker sent an unknown command+my_onmessage(e);return;err("worker sent an unknown command/+g' main-${UNIQVER}.js

rm -rf usr

sed -i "s/@VIAL_VER@/${VIAL_VER}/g" index.html
sed -i "s/@WEB_VER@/${WEB_VER}/g" index.html
sed -i "s/@VIA_STACK_VER@/${VIA_STACK_VER}/g" index.html
sed -i "s/@UNIQVER@/${UNIQVER}/g" index.html

popd
