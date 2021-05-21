FROM python:3

ENV HOME /root

WORKDIR /root

COPY . .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

EXPOSE 8000

CMD ["python3", "-u", "server.py"]