"""Print a Mermaid ER diagram of the database, generated from the Django models.

Usage (from the smart-dispatch folder): python scripts/erd.py > docs/diagrams/erd.mmd
"""
import django, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.apps import apps
APPS = ["accounts", "dispatch", "loadboard", "copilot", "engine"]
SKIP = {"password", "last_login", "is_superuser", "is_staff", "date_joined", "groups", "user_permissions", "first_name", "last_name"}
TYPES = {"BigAutoField": "int", "CharField": "string", "EmailField": "string", "URLField": "string", "TextField": "text",
         "DecimalField": "decimal", "FloatField": "float", "PositiveIntegerField": "int", "IntegerField": "int",
         "BigIntegerField": "int", "BooleanField": "bool", "DateTimeField": "datetime", "DateField": "date",
         "FileField": "file", "ForeignKey": "int", "OneToOneField": "int"}
out, rels = ["erDiagram"], []
for m in apps.get_models():
    if m._meta.app_label not in APPS:
        continue
    name = m.__name__.upper()
    out.append(f"    {name} {{")
    for f in m._meta.concrete_fields:
        if f.name in SKIP:
            continue
        t = TYPES.get(f.get_internal_type(), "string")
        key = "PK" if f.primary_key else "FK" if f.is_relation else ("UK" if f.unique else "")
        col = f.column
        out.append(f"        {t} {col}{' ' + key if key else ''}")
        if f.is_relation:
            target = f.related_model.__name__.upper()
            card = "||--o|" if f.one_to_one else "||--o{"
            rels.append(f'    {target} {card} {name} : "{f.name}"')
    out.append("    }")
print("\n".join(out + sorted(set(rels))))
