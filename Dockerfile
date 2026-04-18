FROM python:3.13-slim

# Dépendances système + git + Docker CLI (pour le bouton de mise à jour)
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils ffmpeg git ca-certificates curl \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
        https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python
COPY web/requirements.txt /app/requirements.txt
RUN pip install --upgrade "pip==24.3.1" \
    && pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY web/ /app

EXPOSE 8080

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "wsgi:app"]
