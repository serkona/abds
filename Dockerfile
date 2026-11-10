ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["python", "-m", "app"]
