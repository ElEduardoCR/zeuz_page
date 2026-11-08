"""Local design preview. Never loads production secrets or payment credentials.
Run: .venv/bin/python design-review/preview.py
Optional screenshot fixtures: ?preview_scheme=light|dark&preview_text=200
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# The preview must never load a production .env or connect to the shop database.
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
for key in list(os.environ):
    if key.startswith(('STRIPE_', 'MP_', 'MERCADOPAGO_', 'RESEND_', 'ADMIN_')):
        os.environ.pop(key)
os.environ['DATABASE_URL'] = 'sqlite:////tmp/zeuz-design-preview.db'
os.environ['PAYMENTS_ENABLED'] = 'false'
os.environ['PUBLIC_BASE_URL'] = 'http://127.0.0.1:5088'
os.environ['FLASK_SECRET'] = 'local-design-preview-only'
from app import app
from flask import request

@app.after_request
def preview_appearance(response):
    # These fixtures exist only in this local runner, not the production app.
    if response.mimetype != 'text/html':
        return response
    styles = ''
    scheme = request.args.get('preview_scheme')
    if scheme == 'light':
        css = (ROOT / 'static/css/design.css').read_text()
        tokens = css.split(':root {', 1)[1].split('}', 1)[0]
        styles += ':root {' + tokens + 'color-scheme:light;}'
    # The marketing design intentionally starts white regardless of OS theme.
    elif scheme == 'dark':
        styles += ':root {color-scheme:light;}'
    if request.args.get('preview_text') == '200':
        styles += 'html {font-size:200%;}'
    if styles:
        response.set_data(response.get_data(as_text=True).replace('</head>', '<style>'+styles+'</style></head>'))
    return response

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5088, debug=False)
