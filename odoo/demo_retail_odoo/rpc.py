"""Thin XML-RPC client for Odoo (standard library only).

Everything the demo does to Odoo goes through the ORM over XML-RPC: no SQL, no Odoo code
imported, nothing Enterprise. The same calls work against any Odoo 17 instance.
"""
import time
import xmlrpc.client

DEFAULT_URL = "http://127.0.0.1:8071"
DEFAULT_DB = "demo_retail"
MASTER_PASSWORD = "admin"       # the docker image default; this instance is a local demo, not a server
ADMIN_LOGIN, ADMIN_PASSWORD = "admin", "admin"


class Odoo:
    def __init__(self, url=DEFAULT_URL, db=DEFAULT_DB, login=ADMIN_LOGIN, password=ADMIN_PASSWORD):
        self.url, self.db, self.login, self.password = url, db, login, password
        self.uid = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common").authenticate(db, login, password, {})
        if not self.uid:
            raise SystemExit(f"login failed: {login}@{db}")
        self._models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    def call(self, model, method, *args, **kwargs):
        return self._models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kwargs)

    def search(self, model, domain, **kw):
        return self.call(model, "search", domain, **kw)

    def search_read(self, model, domain, fields, **kw):
        return self.call(model, "search_read", domain, fields=fields, **kw)

    def read(self, model, ids, fields):
        return self.call(model, "read", ids, fields=fields)

    def create(self, model, vals, context=None):
        return self.call(model, "create", vals, **({"context": context} if context else {}))

    def write(self, model, ids, vals, context=None):
        return self.call(model, "write", ids, vals, **({"context": context} if context else {}))

    def one(self, model, domain, fields):
        rows = self.search_read(model, domain, fields, limit=1)
        return rows[0] if rows else None

    def ref(self, xmlid):
        module, name = xmlid.split(".", 1)
        row = self.one("ir.model.data", [("module", "=", module), ("name", "=", name)], ["res_id"])
        return row["res_id"] if row else None


def wait_ready(url=DEFAULT_URL, timeout=180):
    """Block until the Odoo HTTP/XML-RPC layer answers (the container needs a few seconds)."""
    db = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/db", allow_none=True)
    end = time.time() + timeout
    while True:
        try:
            return db.server_version()
        except Exception:        # connection refused while the container starts
            if time.time() > end:
                raise
            time.sleep(2)


def ensure_database(url=DEFAULT_URL, db_name=DEFAULT_DB, country_code="sk"):
    """Create the database if it does not exist (no Odoo demo data, company country = SK)."""
    db = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/db", allow_none=True)
    if db_name in db.list():
        return False
    db.create_database(MASTER_PASSWORD, db_name, False, "en_US", ADMIN_PASSWORD, ADMIN_LOGIN, country_code)
    return True


def install_modules(odoo, names):
    """Install the Community modules the demo needs. Installing `account` with a Slovak company
    pulls `l10n_sk` (Slovak chart of accounts) in automatically."""
    todo = odoo.search("ir.module.module", [("name", "in", list(names)), ("state", "!=", "installed")])
    if todo:
        odoo.call("ir.module.module", "button_immediate_install", todo)
    return [r["name"] for r in odoo.search_read("ir.module.module", [("name", "in", list(names))], ["name", "state"])
            if r["state"] == "installed"]
