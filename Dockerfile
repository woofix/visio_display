# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.
# See LICENSE file for details

FROM python:3.13-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        poppler-utils ffmpeg openssh-client sshpass postgresql-client smbclient \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY web/requirements.txt /app/requirements.txt
RUN pip install --upgrade "pip==24.3.1" \
    && pip install --no-cache-dir -r requirements.txt

# Application code
COPY web/ /app
COPY scripts/install.sh /app/scripts/install.sh

EXPOSE 8080

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", "--timeout", "600", "wsgi:app"]
