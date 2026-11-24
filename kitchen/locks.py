"""Keeps Ballava's tables private on Postgres services that also publish tables as a web API.

Supabase can serve every table in the "public" schema on the internet to anyone who has the publishable key (which is in
every visitor's browser), unless row-level security is on. Families' kitchens, diets and health goals must never be
readable that way. So after every `migrate` this switches row-level security on for all of Ballava's tables, with no
rules, which means: nobody gets anything, except the app itself (it owns the tables, so the rules don't apply to it).
It also takes away the permissions such services hand out by default.
"""
from django.db import connections

OUTSIDERS = ('anon', 'authenticated')


def lock_tables(using='default'):
    """Returns the tables that were locked. Does nothing on SQLite."""
    connection = connections[using]
    if connection.vendor != 'postgresql':
        return []
    quote = connection.ops.quote_name
    with connection.cursor() as cur:
        cur.execute("SELECT c.relname, c.relrowsecurity, coalesce(c.relacl::text, '') FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') AND pg_get_userbyid(c.relowner) = current_user")
        tables = cur.fetchall()
        for name, locked, _ in tables:
            if not locked:
                cur.execute(f'ALTER TABLE {quote(name)} ENABLE ROW LEVEL SECURITY')
        cur.execute('SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)', [list(OUTSIDERS)])
        for (role,) in cur.fetchall():
            open_to_them = [name for name, _, allowed in tables if f'{role}=' in allowed]
            for name in open_to_them:
                cur.execute(f'REVOKE ALL ON TABLE {quote(name)} FROM {quote(role)}')
            if not open_to_them:
                continue
            cur.execute(f'ALTER DEFAULT PRIVILEGES REVOKE ALL ON TABLES FROM {quote(role)}')
            cur.execute('SELECT current_schema()')
            schema = quote(cur.fetchone()[0])
            cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON TABLES FROM {quote(role)}')
            cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} REVOKE ALL ON SEQUENCES FROM {quote(role)}')
            cur.execute(f'REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema} FROM {quote(role)}')
    return [name for name, _, _ in tables]
