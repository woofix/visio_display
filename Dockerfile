# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.
# See LICENSE file for details

FROM python:3.13-slim AS app

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils ffmpeg git curl ca-certificates openssh-client sshpass postgresql-client smbclient \
        fonts-dejavu-core fonts-dejavu-extra fonts-liberation2 fonts-noto-core fonts-roboto fonts-open-sans fonts-lato fonts-cantarell \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY web/requirements.txt /app/requirements.txt
RUN pip install --upgrade "pip==24.3.1" \
    && pip install --no-cache-dir -r requirements.txt

# Application code
COPY web/ /app
COPY VERSION /VERSION
COPY scripts/ /app/scripts/
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh /app/scripts/*.sh

EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec gunicorn -w \"${GUNICORN_WORKERS:-2}\" -b 0.0.0.0:8080 --timeout 600 --preload wsgi:app"]


FROM app AS updater

RUN apt-get update && apt-get install -y --no-install-recommends \
        docker-cli docker-compose \
    && rm -rf /var/lib/apt/lists/*

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8090", "--timeout", "3600", "services.updater_server:app"]
