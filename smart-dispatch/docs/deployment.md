# Putting Sean AI online

A live link lets your supervisor and markers try the system without installing anything. These steps
use **PythonAnywhere** (free plan for Python websites). Other hosts (Render, Railway) work similarly.

> Check PythonAnywhere's current plan limits before you rely on them. On the free plan, outbound
> internet access is limited to an allow-list of sites, so the AI writing, real email or the Telegram
> bot may not work there; the website itself works. The Telegram bot also needs an always-on task,
> which is a paid feature. For the demo video, running the bot on your own PC is enough.

## 1. Create the account and get the code

1. Sign up at pythonanywhere.com (free "Beginner" account). Your site will be `yourname.pythonanywhere.com`.
2. Open a **Bash console** and run:

```bash
git clone -b claude/cool-goldberg-czu1lr https://github.com/Sherzodbek1717/WIUT.git
cd WIUT/smart-dispatch
python3.13 -m venv .venv          # use the newest Python PythonAnywhere offers (3.10+)
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Settings for a real server

Generate a secret key (keep it private, never put it on GitHub):

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## 3. Create the web app

1. **Web** tab → **Add a new web app** → **Manual configuration** → same Python version.
2. **Virtualenv**: `/home/yourname/WIUT/smart-dispatch/.venv`
3. **Static files**: URL `/static/` → directory `/home/yourname/WIUT/smart-dispatch/staticfiles`
4. Open the **WSGI configuration file** link and replace its contents with:

```python
import os, sys
path = "/home/yourname/WIUT/smart-dispatch"
if path not in sys.path:
    sys.path.insert(0, path)
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DJANGO_DEBUG"] = "0"
os.environ["DJANGO_SECRET_KEY"] = "paste-the-secret-key-here"
os.environ["DJANGO_ALLOWED_HOSTS"] = "yourname.pythonanywhere.com"
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

5. Back in the Bash console (still in `smart-dispatch`, venv active), with the same three variables set:

```bash
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY="paste-the-secret-key-here" DJANGO_ALLOWED_HOSTS=yourname.pythonanywhere.com
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_demo --reset
python manage.py check --deploy
```

6. **Web** tab → turn on **Force HTTPS** → **Reload**. Open `https://yourname.pythonanywhere.com`.

## 4. Before sharing the link

- Change the demo passwords (`demo12345`) in **Users** or `python manage.py changepassword dispatcher`.
- Refresh demo loads before a demo: `python manage.py seed_marketplace`.
- Never commit `db.sqlite3`, secret keys or API keys.
