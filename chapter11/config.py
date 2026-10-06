# Listing 11.1 -- config.py: configuration comes from the environment,
# never from the code. The SAME built artifact runs in development, staging,
# and production; only the environment differs. This is what makes the
# thing you tested (Chapter 10) the exact thing you deploy -- if config
# were baked in, each environment would run different code.
import os

class Config:
    def __init__(self, env=None):
        env = env or os.environ

        # Required: no default. A missing critical value should CRASH at
        # startup, loudly, not fail mysteriously on the first request.
        self.database_url = self._require(env, "ENCORE_DATABASE_URL")

        # Optional: sensible defaults, overridable per environment.
        self.port = int(env.get("ENCORE_PORT", "3000"))
        self.payment_url = env.get("ENCORE_PAYMENT_URL",
                                   "http://localhost:4000")
        self.hold_seconds = int(env.get("ENCORE_HOLD_SECONDS", "900"))
        self.log_level = env.get("ENCORE_LOG_LEVEL", "info")

        # Secrets come from the environment too -- NEVER from the repo.
        # (In production, injected by the platform's secret manager.)
        self.payment_api_key = env.get("ENCORE_PAYMENT_API_KEY", "")

    @staticmethod
    def _require(env, name):
        value = env.get(name)
        if not value:
            raise SystemExit(
                f"FATAL: {name} is required and unset. "
                f"Refusing to start with incomplete configuration.")
        return value

    def redacted(self):
        """For logging at startup: prove what we loaded WITHOUT leaking
        secrets. You want this line in every deploy's logs."""
        return {"port": self.port, "database": _hostpart(self.database_url),
                "payment_url": self.payment_url,
                "hold_seconds": self.hold_seconds,
                "payment_api_key": "***" if self.payment_api_key else "(unset)"}

def _hostpart(url):
    # show which database, not the password in the URL
    return url.split("@")[-1] if "@" in url else url

if __name__ == "__main__":
    # Demo: a good config, and a fatal missing one.
    good = Config({"ENCORE_DATABASE_URL":
                   "postgresql://encore:secret@db.prod:5432/encore",
                   "ENCORE_PORT": "8080"})
    import json
    print("loaded config:", json.dumps(good.redacted()))
    print("note: password not shown, even though it was in the URL")
    try:
        Config({"ENCORE_PORT": "8080"})       # missing the required URL
    except SystemExit as e:
        print("\nmissing required value ->", e)
