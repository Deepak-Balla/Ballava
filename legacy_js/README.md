# Old JavaScript version (kept for reference)

Ballava's server and cooking logic used to be JavaScript (Node.js). They now live in Python:

| Old (JavaScript)              | New (Python)                                  |
|-------------------------------|-----------------------------------------------|
| `server/server.mjs`           | Django: `config/` and `kitchen/api.py`        |
| `server/accounts.mjs`, `auth.mjs`, `db.mjs` | `kitchen/api.py`, `kitchen/models.py`, `kitchen/security.py` |
| `server/ai.mjs`               | `kitchen/ai.py`                               |
| `shared/engine.mjs`           | `kitchen/engine.py`                           |
| `shared/planner.mjs`          | `kitchen/planner.py`                          |
| `shared/recipes*.mjs`, `ingredients.mjs`, `rescue.mjs` | `kitchen/data/*.py`      |
| custom admin page             | Django admin at `/admin`                      |
| `tests/*.mjs`                 | `kitchen/tests/test_*.py` (pytest)            |

`data/ballava.db` here is the old database. Its accounts can't be moved across, because passwords are
stored in a different, one-way scrambled format. Nothing in the new app uses this folder.
Delete it whenever you like.
