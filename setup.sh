#!/bin/bash

# ═══════════════════════════════════════════════════════════════════
# LINUP macOS - Setup & Build
# ═══════════════════════════════════════════════════════════════════

set -e

echo "════════════════════════════════════════════════════════════"
echo "  LINUP macOS - Configuración del Environment"
echo "════════════════════════════════════════════════════════════"
echo ""

# 1. Verify Python
echo "[1/5] Verificando Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no encontrado. Instálalo con: brew install python@3.11"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Python $PYTHON_VERSION encontrado"
echo ""

# 2. Create virtual environment
echo "[2/5] Creando entorno virtual..."
if [ -d "venv" ]; then
    echo "⚠️  El entorno virtual ya existe, usando el existente"
else
    python3 -m venv venv
    echo "✓ Entorno virtual creado"
fi
echo ""

# 3. Install dependencies
echo "[3/5] Instalando dependencias..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install "flet>=0.25.0"
echo "✓ Flet instalado"
echo ""

# 4. Verify Flutter (required for macOS build)
echo "[4/5] Verificando Flutter..."
if ! command -v flutter &> /dev/null; then
    echo "⚠️  Flutter no encontrado"
    echo "   Instálalo con: brew install --cask flutter"
    echo "   O desde: https://docs.flutter.dev/get-started/install/macos"
else
    FLUTTER_VERSION=$(flutter --version 2>/dev/null | head -n1 | cut -d' ' -f2)
    echo "✓ Flutter $FLUTTER_VERSION encontrado"
fi
echo ""

# 5. Summary
echo "[5/5] Resumen"
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
