FROM python:3.12-slim

WORKDIR /app

COPY choosing /app/choosing

ENV HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["python", "-m", "choosing.api"]
