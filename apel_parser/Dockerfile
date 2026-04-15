FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd -g 1000 apeluser && \
    useradd -u 1000 -g apeluser apeluser
RUN chown -R apeluser:apeluser /app
USER apeluser
