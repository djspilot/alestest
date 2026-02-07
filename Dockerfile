FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# System dependencies + FreeCAD
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    freecad \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# FreeCAD SheetMetal workbench (required for unfold)
RUN mkdir -p /root/.local/share/FreeCAD/Mod && \
    git clone --depth 1 https://github.com/shaise/FreeCAD_SheetMetal.git \
    /root/.local/share/FreeCAD/Mod/sheetmetal

# FreeCAD path on Debian
ENV FREECAD_PATH=/usr/lib/freecad

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt requirements-api.txt ./
RUN pip3 install --no-cache-dir --break-system-packages \
    -r requirements.txt -r requirements-api.txt

# Copy application code
COPY manufacturing_pipeline/ manufacturing_pipeline/
COPY api/ api/
COPY run.py ./

# Create necessary directories
RUN mkdir -p /tmp/manufacturing-uploads resources/output resources/data

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
