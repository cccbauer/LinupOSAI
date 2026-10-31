#!/bin/bash

# ═══════════════════════════════════════════════════════════════════
# LINUP macOS - Setup & Build
# ═══════════════════════════════════════════════════════════════════

set -e

echo "════════════════════════════════════════════════════════════"
echo "  LINUP macOS - Configuración del Environment"
echo "════════════════════════════════════════════════════════════"
echo ""

# flet requires Python >= 3.10
MIN_PY_MINOR=10
PREFERRED_PY_VERSION="3.11"

version_ok() {
    # $1 = "3.9", "3.11", etc.
    local minor="${1#3.}"
    [ "$minor" -ge "$MIN_PY_MINOR" ] 2>/dev/null
}

# 0. Verify Homebrew (installing it if missing) and Git
echo "[1/7] Verificando Homebrew..."
if ! command -v brew &> /dev/null; then
    echo "⚠️  Homebrew no encontrado, instalándolo..."
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    if [ -x /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -x /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi

    if ! command -v brew &> /dev/null; then
        echo "❌ No se pudo instalar Homebrew automáticamente."
        echo "   Instálalo manualmente desde: https://brew.sh"
        exit 1
    fi
fi
echo "✓ Homebrew encontrado ($(brew --version | head -n1))"
echo ""

echo "[2/7] Verificando Git..."
if ! command -v git &> /dev/null; then
    echo "⚠️  Git no encontrado, instalándolo con Homebrew..."
    brew install git
fi
echo "✓ Git encontrado ($(git --version))"
echo ""

# 1. Find a Python >= 3.10, installing one via brew if needed
echo "[3/7] Verificando Python..."

PYTHON_BIN=""
for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &> /dev/null; then
        v=$("$candidate" --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        if version_ok "$v"; then
            PYTHON_BIN="$candidate"
            PYTHON_VERSION="$v"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "⚠️  No se encontró Python >= 3.$MIN_PY_MINOR (flet lo requiere)"
    if command -v brew &> /dev/null; then
        echo "   Instalando python@$PREFERRED_PY_VERSION con Homebrew..."
        brew install "python@$PREFERRED_PY_VERSION"
        PYTHON_BIN="$(brew --prefix python@$PREFERRED_PY_VERSION)/bin/python$PREFERRED_PY_VERSION"
        if [ ! -x "$PYTHON_BIN" ]; then
            echo "❌ No se pudo instalar Python $PREFERRED_PY_VERSION automáticamente."
            echo "   Instálalo manualmente con: brew install python@$PREFERRED_PY_VERSION"
            exit 1
        fi
        PYTHON_VERSION="$PREFERRED_PY_VERSION"
    else
        echo "❌ Homebrew no encontrado, no se puede instalar Python automáticamente."
        echo "   Instala Homebrew (https://brew.sh) o Python >= 3.$MIN_PY_MINOR manualmente."
        exit 1
    fi
fi
echo "✓ Usando Python $PYTHON_VERSION ($PYTHON_BIN)"
echo ""

# 2. Create virtual environment
echo "[4/7] Creando entorno virtual..."
if [ -d "venv" ]; then
    VENV_PY_VERSION=$(venv/bin/python3 --version 2>/dev/null | cut -d' ' -f2 | cut -d'.' -f1,2)
    if version_ok "$VENV_PY_VERSION"; then
        echo "⚠️  El entorno virtual ya existe (Python $VENV_PY_VERSION), usando el existente"
    else
        echo "⚠️  El entorno virtual existente usa Python $VENV_PY_VERSION (< 3.$MIN_PY_MINOR), recreándolo..."
        rm -rf venv
        "$PYTHON_BIN" -m venv venv
        echo "✓ Entorno virtual recreado"
    fi
else
    "$PYTHON_BIN" -m venv venv
    echo "✓ Entorno virtual creado"
fi
echo ""

# 3. Install dependencies
echo "[5/7] Instalando dependencias..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install "flet==0.80.5" "reportlab>=4.0.0"
echo "✓ Flet instalado"
echo ""

# 4. Verify Flutter + CocoaPods (required for `flet build macos`), installing via brew if missing
echo "[6/7] Verificando Flutter y CocoaPods..."
if ! command -v flutter &> /dev/null; then
    echo "⚠️  Flutter no encontrado, instalándolo con Homebrew..."
    brew install --cask flutter
fi
FLUTTER_VERSION=$(flutter --version 2>/dev/null | head -n1 | cut -d' ' -f2)
echo "✓ Flutter $FLUTTER_VERSION encontrado"

if ! command -v pod &> /dev/null; then
    echo "⚠️  CocoaPods no encontrado, instalándolo con Homebrew..."
    brew install cocoapods
fi
echo "✓ CocoaPods encontrado ($(pod --version 2>/dev/null))"

if ! xcodebuild -version &> /dev/null; then
    echo "⚠️  Xcode completo no encontrado (solo Command Line Tools)."
    echo "   flet build macos lo requiere. Instálalo desde la App Store,"
    echo "   luego ejecuta: sudo xcode-select -s /Applications/Xcode.app"
fi
echo ""

# 5. Summary
echo "[7/7] Resumen"
echo "════════════════════════════════════════════════════════════"
echo "Python:    $PYTHON_VERSION"
echo "Flet:      $(pip show flet 2>/dev/null | grep Version | cut -d' ' -f2)"
echo "Proyecto:  $(pwd)"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "✅ Environment listo!"
echo ""
echo "COMANDOS:"
echo "  Activar entorno:    source venv/bin/activate"
echo "  Probar (ventana):   flet run main.py"
echo "  Compilar .app:      flet build macos"
echo ""
echo "El .app quedará en: build/macos/Linup.app"
echo ""
