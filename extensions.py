# extensions.py — shared Flask extensions (avoids circular imports)
# Import this module in app.py and in blueprints that need limiter/csrf.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

# Initialised without an app — call init_app(app) in app.py
limiter = Limiter(
    key_func=get_remote_address,
    # Generous global limit: ~33 req/s is plenty for any single user.
    # Sensitive auth endpoints override this with stricter limits below.
    default_limits=["2000 per minute"],
    storage_uri="memory://",
)

csrf = CSRFProtect()
