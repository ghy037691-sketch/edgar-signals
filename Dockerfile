FROM apify/actor-python:3.12

# No third-party dependencies — standard library only.
COPY . /usr/src/app
WORKDIR /usr/src/app

CMD ["python3", "main.py"]
