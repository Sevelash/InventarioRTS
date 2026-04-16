"""
Servidor de producción — usa Waitress (multiplataforma, no dev-server).
Ejecutar con:  python serve.py
"""
import os

# Lee variables de entorno si existe python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

port = int(os.environ.get('PORT', 5050))
debug = os.environ.get('DEBUG', 'False').lower() == 'true'

if debug:
    # Desarrollo
    from app import app
    app.run(debug=True, port=port)
else:
    # Producción — Waitress (Windows) o Gunicorn (Linux)
    try:
        from waitress import serve
        from app import app
        print(f'✅  RTS Asset Management corriendo en http://0.0.0.0:{port}')
        print('    Presiona Ctrl+C para detener.')
        serve(app, host='0.0.0.0', port=port, threads=4)
    except ImportError:
        # Fallback: gunicorn (Linux)
        import subprocess, sys
        subprocess.run([sys.executable, '-m', 'gunicorn',
                        '-w', '2', '-b', f'0.0.0.0:{port}', 'app:app'])
