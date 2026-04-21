FROM python:3.13-slim

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils ffmpeg openssh-client sshpass \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python
COPY web/requirements.txt /app/requirements.txt
RUN pip install --upgrade "pip==24.3.1" \
    && pip install --no-cache-dir -r requirements.txt

# Code applicatif
COPY web/ /app
COPY install.sh /app/install.sh
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

RUN chmod +x /app/install.sh /app/docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "wsgi:app"]
