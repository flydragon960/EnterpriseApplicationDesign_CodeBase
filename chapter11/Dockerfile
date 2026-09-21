# Listing 11.4 -- Dockerfile: the service as a portable, immutable artifact.
# The image is built ONCE and run everywhere unchanged (Chapter 10's tested
# thing IS the deployed thing). Notes on each choice follow the book.

# Pin a specific base -- 'python:3.12-slim', never ':latest'. A floating tag
# means the artifact is not reproducible: rebuild tomorrow, get a different
# base, and "it worked yesterday" becomes unfalsifiable.
FROM python:3.12-slim

# A non-root user: if the process is compromised, it is not root in the
# container. Least privilege (Chapter 8) at the deployment layer.
RUN useradd --create-home --uid 10001 encore
WORKDIR /app

# Dependencies BEFORE code, as their own layer: they change rarely, so this
# layer caches across builds and only code changes trigger a reinstall.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now the code.
COPY --chown=encore:encore . .
USER encore

# Config comes from the environment at RUN time, never baked in (Listing 11.1).
# Only a default port is declared; everything else is injected per environment.
ENV ENCORE_PORT=3000
EXPOSE 3000

# The orchestrator will call /healthz and /readyz (Listing 11.2); declaring
# the health check here documents the contract and lets plain Docker use it.
HEALTHCHECK --interval=10s --timeout=2s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://localhost:3000/healthz').status==200 else 1)"

# A production WSGI server, not Flask's dev server. Exec form so the process
# is PID 1 and receives SIGTERM directly -- which Listing 11.2 handles to
# drain gracefully.
CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "4", \
     "--graceful-timeout", "30", "app:app"]
